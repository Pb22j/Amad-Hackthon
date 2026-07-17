"""``monthly_report`` — summarize what the user paid and received in a month.

The report aggregates the owner's ledger for one calendar month: totals for
money out (debits) and money in (credits), the net change, a per-category
breakdown, and the individual transactions. Months with no activity still
return a valid empty report rather than an error.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    BankConnection,
    find_user_by_username,
    money,
    month_bounds,
    next_reference,
    owner_identity,
    run_in_bank_db,
    tool_result,
    riyadh_now,
)

_MAX_LISTED_TRANSACTIONS = 50


class MonthlyReportArgs(BankToolArgs):
    month: str | None = Field(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Report month in YYYY-MM format. Defaults to the current month.",
    )


async def monthly_report(month: str | None = None) -> dict[str, Any]:
    """Build the paid/received summary for one calendar month."""

    username, _ = owner_identity()
    report_month = month or riyadh_now().strftime("%Y-%m")
    start, end = month_bounds(report_month)

    def work(connection: BankConnection) -> dict[str, Any]:
        owner = find_user_by_username(connection, username)
        if owner is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )

        rows = connection.execute(
            "SELECT * FROM transactions"
            " WHERE user_uuid = %s AND createdAt >= %s AND createdAt < %s"
            " ORDER BY createdAt",
            (owner["uuid"], start, end),
        ).fetchall()

        total_paid = Decimal("0.00")
        total_received = Decimal("0.00")
        categories: dict[str, dict[str, Decimal]] = {}
        transactions: list[dict[str, Any]] = []
        for row in rows:
            amount = money(row["Amount_SAR"])
            bucket = categories.setdefault(
                row["Category"], {"paid": Decimal("0.00"), "received": Decimal("0.00")}
            )
            if row["direction"] == "debit":
                total_paid += amount
                bucket["paid"] += amount
            else:
                total_received += amount
                bucket["received"] += amount
            transactions.append(
                {
                    "date": row["createdAt"],
                    "direction": row["direction"],
                    "type": row["Transaction_Type"],
                    "amount_sar": str(amount),
                    "counterparty": row["Counterparty_Name"],
                    "description": row["Description"],
                    "category": row["Category"],
                    "reference": row["Reference"],
                }
            )

        listed = transactions[:_MAX_LISTED_TRANSACTIONS]
        data = {
            "month": report_month,
            "account_number": owner["nafi_iban"],
            "nafi_iban": owner["nafi_iban"],
            "currency": "SAR",
            "total_paid_sar": str(total_paid),
            "total_received_sar": str(total_received),
            "net_sar": str(total_received - total_paid),
            "transaction_count": len(transactions),
            "categories": {
                name: {"paid_sar": str(values["paid"]), "received_sar": str(values["received"])}
                for name, values in sorted(categories.items())
            },
            "transactions": listed,
            "truncated": len(transactions) > len(listed),
            "current_nafi_balance_sar": str(money(owner["nafi_balance"])),
            "current_balance_sar": str(money(owner["nafi_balance"])),
        }
        return tool_result(
            status="completed",
            summary=(
                f"Monthly report for {report_month}: paid {total_paid} SAR, "
                f"received {total_received} SAR across {len(transactions)} transactions."
            ),
            data=data,
            operation_id=next_reference(connection, "report"),
        )

    return await run_in_bank_db(work)


TOOL: BaseTool = StructuredTool.from_function(
    coroutine=monthly_report,
    name="monthly_report",
    description=(
        "Generate the authenticated user's monthly statement: total paid, total received, "
        "net change, category breakdown, and the month's transactions. Defaults to the "
        "current month when no month is given."
    ),
    args_schema=MonthlyReportArgs,
)
