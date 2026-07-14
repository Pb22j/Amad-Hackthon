"""``pay_fatoorah`` / ``list_fatoorahs`` — pay the user's assigned bills.

Every fatoorah (bill) in the database has a purely numeric SADAD-style bill
number and is assigned to exactly one bank customer, so a user can only see
and pay their own bills. To pay, the user must state the **last four digits**
of the bill number — that is how the bill is selected. Payment deducts the
bill amount from the user's balance (rejected if the balance cannot cover it)
and records a ledger entry under the "فواتير" category, so it appears in the
monthly report. Fatoorah payments are fully exempt from the daily spend limit
by design — neither checked against it nor counted toward it.
"""

from __future__ import annotations

import sqlite3
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    find_user_by_username,
    money,
    next_reference,
    owner_identity,
    run_in_bank_db,
    timestamp,
    tool_result,
)


class PayFatoorahArgs(BankToolArgs):
    last_four_digits: str = Field(
        min_length=4,
        max_length=4,
        pattern=r"^[0-9]{4}$",
        description=(
            "The last four digits of the bill number, exactly as the user stated "
            "them. Bill numbers are numeric only."
        ),
    )


class ListFatoorahsArgs(BankToolArgs):
    pass


def _fatoorah_view(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "bill_number": row["Bill_Number"],
        "biller": row["Biller_Name_Ar"],
        "amount_sar": str(money(row["Amount_SAR"])),
        "status": "مدفوعة" if row["status"] == "paid" else "غير مدفوعة",
        "due_date": row["dueDate"],
        "paid_at": row["paidAt"],
    }


async def pay_fatoorah(last_four_digits: str) -> dict[str, Any]:
    """Pay the caller's bill selected by the last four digits of its number."""

    username, _ = owner_identity()
    digits = last_four_digits.strip()

    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        # The schema enforces four numeric digits; this guards direct calls.
        if not (len(digits) == 4 and digits.isdigit()):
            return tool_result(
                status="failed",
                summary="The bill must be selected by exactly four numeric digits.",
                data={"last_four_digits": digits},
                error_code="invalid_bill_digits",
            )

        payer = find_user_by_username(connection, username)
        if payer is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        if payer["status"] != "active":
            return tool_result(
                status="failed",
                summary="The account is not active, so it cannot pay bills.",
                data={},
                error_code="source_account_inactive",
            )

        # Bills are assigned to one customer; only the owner's bills match.
        matches = connection.execute(
            "SELECT * FROM fatoorahs"
            " WHERE user_uuid = ? AND substr(Bill_Number, -4) = ?"
            " ORDER BY createdAt",
            (payer["uuid"], digits),
        ).fetchall()
        unpaid = [row for row in matches if row["status"] == "unpaid"]
        if not unpaid:
            if matches:
                return tool_result(
                    status="failed",
                    summary="This fatoorah is already paid.",
                    data={"last_four_digits": digits, "status": "مدفوعة"},
                    error_code="already_paid",
                )
            return tool_result(
                status="failed",
                summary=(
                    "No bill assigned to the user ends with these four digits."
                ),
                data={"last_four_digits": digits},
                error_code="fatoorah_not_found",
            )
        if len(unpaid) > 1:
            return tool_result(
                status="failed",
                summary=(
                    "More than one unpaid bill ends with these digits; the user "
                    "must disambiguate by biller."
                ),
                data={
                    "last_four_digits": digits,
                    "candidates": [
                        {"biller": row["Biller_Name_Ar"], "bill_number": row["Bill_Number"]}
                        for row in unpaid
                    ],
                },
                error_code="ambiguous_bill_digits",
            )
        fatoorah = unpaid[0]
        amount = money(fatoorah["Amount_SAR"])

        # Fatoorah payments bypass the daily spend limit; only the balance rules.
        balance = money(payer["Balance_SAR"])
        if amount > balance:
            return tool_result(
                status="failed",
                summary="The available balance is not enough to pay this fatoorah.",
                data={
                    "bill_amount_sar": str(amount),
                    "available_balance_sar": str(balance),
                },
                error_code="insufficient_funds",
            )

        reference = next_reference(connection, "fatoorah")
        now = timestamp()
        balance_after = balance - amount
        connection.execute(
            "UPDATE users SET Balance_SAR = ?, updatedAt = ? WHERE uuid = ?",
            (float(balance_after), now, payer["uuid"]),
        )
        connection.execute(
            "UPDATE fatoorahs SET status = 'paid', paidAt = ? WHERE uuid = ?",
            (now, fatoorah["uuid"]),
        )
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (?, ?, ?, 'debit', 'fatoorah_payment', ?, ?, NULL, ?, 'فواتير', ?, ?, ?)",
            (
                str(uuid4()),
                payer["uuid"],
                payer["Account_Number"],
                float(amount),
                fatoorah["Biller_Name_Ar"],
                f"سداد فاتورة {fatoorah['Biller_Name_Ar']} رقم {fatoorah['Bill_Number']}",
                float(balance_after),
                reference,
                now,
            ),
        )

        return tool_result(
            status="completed",
            summary=(
                f"Paid the {fatoorah['Biller_Name_Ar']} fatoorah ending in {digits} "
                f"({amount} SAR)."
            ),
            data={
                "bill_number": fatoorah["Bill_Number"],
                "biller": fatoorah["Biller_Name_Ar"],
                "amount_sar": str(amount),
                "bill_status": "مدفوعة",
                "new_balance_sar": str(balance_after),
                "reference": reference,
                "executed_at": now,
            },
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


async def list_fatoorahs() -> dict[str, Any]:
    """List the bills assigned to the authenticated user."""

    username, _ = owner_identity()

    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        rows = connection.execute(
            "SELECT * FROM fatoorahs WHERE user_uuid = ?"
            " ORDER BY status DESC, createdAt",
            (user["uuid"],),
        ).fetchall()
        bills = [_fatoorah_view(row) for row in rows]
        unpaid_total = sum(
            (money(row["Amount_SAR"]) for row in rows if row["status"] == "unpaid"),
            money(0),
        )
        return tool_result(
            status="completed",
            summary=(
                f"Found {len(bills)} fatoorahs for the user; unpaid total "
                f"{unpaid_total} SAR."
            ),
            data={"fatoorahs": bills, "unpaid_total_sar": str(unpaid_total)},
            operation_id=next_reference(connection, "fatoorah-list"),
        )

    return await run_in_bank_db(work)


PAY_FATOORAH_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=pay_fatoorah,
    name="pay_fatoorah",
    description=(
        "Pay one of the authenticated user's assigned bills (فاتورة) after "
        "confirmation. The user must state the last four digits of the numeric bill "
        "number to select which bill to pay. The amount is deducted from the balance "
        "and appears in the monthly report; fatoorah payments are exempt from the "
        "daily spend limit."
    ),
    args_schema=PayFatoorahArgs,
)

LIST_FATOORAHS_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=list_fatoorahs,
    name="list_fatoorahs",
    description=(
        "List the bills (فواتير) assigned to the authenticated user with their "
        "numbers, billers, amounts, due dates, and payment status."
    ),
    args_schema=ListFatoorahsArgs,
)
