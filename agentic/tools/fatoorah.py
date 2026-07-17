"""``pay_fatoorah`` / ``list_fatoorahs`` — pay the user's assigned bills.

Every fatoorah (bill) is assigned to exactly one bank customer, so a user can
only see and pay their own bills. A bill is selected by its biller name; the
customer never has to provide digits from the bill number. Payment deducts the
bill amount from the user's Nafi wallet (rejected if its balance cannot cover
it) and records a ledger entry under the "فواتير" category, so it appears in
the monthly report. Bill-payment debits count toward the customer's daily
limit.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    BankConnection,
    BankRow,
    find_user_by_username,
    money,
    next_reference,
    owner_identity,
    run_in_bank_db,
    spent_today,
    timestamp,
    tool_result,
    update_nafi_balance,
)
from agentic.tools.entity_resolution import normalize_entity_text, resolve_entity


class PayFatoorahArgs(BankToolArgs):
    biller: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "The biller or service-provider name exactly as the user stated it, "
            "for example الكهرباء, STC, or شركة المياه."
        ),
    )


class ListFatoorahsArgs(BankToolArgs):
    pass


def _fatoorah_view(row: BankRow) -> dict[str, Any]:
    return {
        "bill_number": row["Bill_Number"],
        "biller": row["Biller_Name_Ar"],
        "amount_sar": str(money(row["Amount_SAR"])),
        "status": "مدفوعة" if row["status"] == "paid" else "غير مدفوعة",
        "due_date": row["dueDate"],
        "paid_at": row["paidAt"],
    }


def _biller_labels(row: BankRow) -> tuple[str, ...]:
    """Return safe natural-language aliases derived from a stored biller name."""

    biller = str(row["Biller_Name_Ar"])
    labels = {biller}
    for token in normalize_entity_text(biller).split():
        labels.add(token)
        without_prefix = token
        if len(without_prefix) > 3 and without_prefix[0] in {"و", "ل", "ب", "ك"}:
            without_prefix = without_prefix[1:]
            labels.add(without_prefix)
        if len(without_prefix) > 4 and without_prefix.startswith("ال"):
            labels.add(without_prefix[2:])
    return tuple(labels)


async def pay_fatoorah(biller: str) -> dict[str, Any]:
    """Pay the caller's bill selected by its biller or service-provider name."""

    username, _ = owner_identity()
    requested_biller = biller.strip()

    def work(connection: BankConnection) -> dict[str, Any]:
        if not requested_biller:
            return tool_result(
                status="failed",
                summary="A biller name is required to select the fatoorah.",
                data={"biller": requested_biller},
                error_code="invalid_biller",
            )

        payer = find_user_by_username(connection, username)
        if payer is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        # Bills are assigned to one customer; only the owner's bills are ever
        # considered by the natural-language resolver.
        rows = connection.execute(
            "SELECT * FROM fatoorahs WHERE user_uuid = %s ORDER BY createdAt",
            (payer["uuid"],),
        ).fetchall()
        unpaid_resolution = resolve_entity(
            requested_biller,
            (row for row in rows if row["status"] == "unpaid"),
            labels=_biller_labels,
        )
        if unpaid_resolution.match is None:
            if unpaid_resolution.candidates:
                return tool_result(
                    status="failed",
                    summary=(
                        "More than one unpaid bill matches this biller; the user "
                        "must choose a more specific biller name."
                    ),
                    data={
                        "biller": requested_biller,
                        "candidates": [_fatoorah_view(row) for row in unpaid_resolution.candidates],
                    },
                    error_code="ambiguous_biller",
                )

            paid_resolution = resolve_entity(
                requested_biller,
                (row for row in rows if row["status"] == "paid"),
                labels=_biller_labels,
            )
            if paid_resolution.match is not None or paid_resolution.candidates:
                return tool_result(
                    status="failed",
                    summary="This fatoorah is already paid.",
                    data={"biller": requested_biller, "status": "مدفوعة"},
                    error_code="already_paid",
                )
            return tool_result(
                status="failed",
                summary="No bill assigned to the user matches this biller.",
                data={"biller": requested_biller},
                error_code="fatoorah_not_found",
            )
        fatoorah = unpaid_resolution.match
        amount = money(fatoorah["Amount_SAR"])

        balance = money(payer["nafi_balance"])
        if amount > balance:
            return tool_result(
                status="failed",
                summary="The available Nafi wallet balance is not enough to pay this fatoorah.",
                data={
                    "bill_amount_sar": str(amount),
                    "available_balance_sar": str(balance),
                },
                error_code="insufficient_funds",
            )
        daily_limit = money(payer["Daily_Spend_Limit_SAR"])
        already_spent = spent_today(connection, payer["uuid"])
        if already_spent + amount > daily_limit:
            return tool_result(
                status="failed",
                summary="This bill payment would exceed the daily spend limit.",
                data={
                    "bill_amount_sar": str(amount),
                    "spent_today_sar": str(already_spent),
                    "daily_limit_sar": str(daily_limit),
                },
                error_code="daily_limit_exceeded",
            )

        reference = next_reference(connection, "fatoorah")
        now = timestamp()
        balance_after = balance - amount
        update_nafi_balance(connection, payer, balance_after)
        connection.execute(
            "UPDATE fatoorahs SET status = 'paid', paidAt = %s WHERE uuid = %s",
            (now, fatoorah["uuid"]),
        )
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (%s, %s, %s, 'debit', 'fatoorah_payment', %s, %s, NULL, %s, 'فواتير', %s, %s, %s)",
            (
                str(uuid4()),
                payer["uuid"],
                payer["nafi_iban"],
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
            summary=(f"Paid the {fatoorah['Biller_Name_Ar']} fatoorah ({amount} SAR)."),
            data={
                "bill_number": fatoorah["Bill_Number"],
                "biller": fatoorah["Biller_Name_Ar"],
                "amount_sar": str(amount),
                "bill_status": "مدفوعة",
                "new_nafi_balance_sar": str(balance_after),
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

    def work(connection: BankConnection) -> dict[str, Any]:
        user = find_user_by_username(connection, username)
        if user is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        rows = connection.execute(
            "SELECT * FROM fatoorahs WHERE user_uuid = %s ORDER BY status DESC, createdAt",
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
                f"Found {len(bills)} fatoorahs for the user; unpaid total {unpaid_total} SAR."
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
        "confirmation. Select the bill from the biller or service-provider name; "
        "never ask for digits from the bill number. The amount is deducted only "
        "from the Nafi wallet balance and appears in the monthly report; linked "
        "banks are read-only."
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
