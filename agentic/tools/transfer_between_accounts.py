"""``transfer_between_accounts`` — move money to an activated beneficiary.

The transfer only completes when every database rule passes: the destination
must be an *active* entry in the owner's beneficiary list, the destination
bank account must still exist and be active, the balance must cover the
amount, and the owner's daily spend limit must not be exceeded. Both ledger
entries and both balances are written in one atomic database transaction, and
a completed transfer returns an authoritative receipt.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
    BankConnection,
    BankRow,
    find_beneficiary,
    find_user_by_account_number,
    find_user_by_username,
    money,
    next_reference,
    owner_identity,
    run_in_bank_db,
    spent_today,
    timestamp,
    tool_result,
)


class TransferBetweenAccountsArgs(BankToolArgs):
    destination_account: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Destination account number (IBAN) or the saved beneficiary short name, "
            "exactly as the user stated it."
        ),
    )
    # Declared as float so the JSON schema is a plain number: Decimal renders a
    # look-around regex branch that grammar-constrained providers reject. The
    # tool converts to Decimal and quantizes to two places itself.
    amount: float = Field(
        gt=0,
        le=9_999_999_999,
        description="Amount to transfer in SAR.",
    )


def _validate_transfer(
    connection: BankConnection,
    *,
    username: str,
    destination_account: str,
    amount: Decimal,
) -> tuple[BankRow, BankRow, BankRow, Decimal] | dict[str, Any]:
    """Validate every transfer prerequisite without changing bank state."""

    owner = find_user_by_username(connection, username)
    if owner is None:
        return tool_result(
            status="failed",
            summary="The authenticated customer profile was not found.",
            data={},
            error_code="customer_not_found",
        )
    if owner["status"] != "active":
        return tool_result(
            status="failed",
            summary="The source account is not active, so it cannot send transfers.",
            data={},
            error_code="source_account_inactive",
        )

    beneficiary = find_beneficiary(connection, owner["uuid"], destination_account)
    if beneficiary is None:
        return tool_result(
            status="failed",
            summary=(
                "The destination is not in the beneficiary list. It must be added and "
                "activated with add_benefit before transferring."
            ),
            data={"destination_account": destination_account},
            error_code="beneficiary_not_found",
        )
    if beneficiary["status"] != "active":
        return tool_result(
            status="failed",
            summary="The beneficiary exists but is not activated for transfers.",
            data={"destination_account": beneficiary["Account_Number"]},
            error_code="beneficiary_not_active",
        )

    balance = money(owner["Balance_SAR"])
    if amount > balance:
        return tool_result(
            status="failed",
            summary="The available balance is not enough for this transfer.",
            data={
                "requested_amount_sar": str(amount),
                "available_balance_sar": str(balance),
            },
            error_code="insufficient_funds",
        )

    daily_limit = money(owner["Daily_Spend_Limit_SAR"])
    already_spent = spent_today(connection, owner["uuid"])
    if already_spent + amount > daily_limit:
        return tool_result(
            status="failed",
            summary="This transfer would exceed the daily spend limit.",
            data={
                "requested_amount_sar": str(amount),
                "spent_today_sar": str(already_spent),
                "daily_limit_sar": str(daily_limit),
            },
            error_code="daily_limit_exceeded",
        )

    receiver = find_user_by_account_number(connection, beneficiary["Account_Number"])
    if receiver is None or receiver["status"] != "active":
        return tool_result(
            status="failed",
            summary="The destination bank account is no longer available.",
            data={"destination_account": beneficiary["Account_Number"]},
            error_code="destination_account_unavailable",
        )
    return owner, beneficiary, receiver, balance


async def preflight_transfer_between_accounts(
    destination_account: str, amount: float | Decimal
) -> dict[str, Any]:
    """Check transfer eligibility before asking the user for confirmation."""

    username, _ = owner_identity()
    normalized_amount = money(amount)

    def work(connection: BankConnection) -> dict[str, Any]:
        validation = _validate_transfer(
            connection,
            username=username,
            destination_account=destination_account,
            amount=normalized_amount,
        )
        if isinstance(validation, dict):
            return validation
        return tool_result(
            status="completed",
            summary="Transfer prerequisites validated.",
            data={},
        )

    return await run_in_bank_db(work)


async def transfer_between_accounts(
    destination_account: str, amount: float | Decimal
) -> dict[str, Any]:
    """Execute an atomic transfer from the owner's account to a beneficiary."""

    username, _ = owner_identity()
    amount = money(amount)

    def work(connection: BankConnection) -> dict[str, Any]:
        owner = find_user_by_username(connection, username)
        if owner is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        if owner["status"] != "active":
            return tool_result(
                status="failed",
                summary="The source account is not active, so it cannot send transfers.",
                data={},
                error_code="source_account_inactive",
            )

        beneficiary = find_beneficiary(connection, owner["uuid"], destination_account)
        if beneficiary is None:
            return tool_result(
                status="failed",
                summary=(
                    "The destination is not in the beneficiary list. It must be added and "
                    "activated with add_benefit before transferring."
                ),
                data={"destination_account": destination_account},
                error_code="beneficiary_not_found",
            )
        if beneficiary["status"] != "active":
            return tool_result(
                status="failed",
                summary="The beneficiary exists but is not activated for transfers.",
                data={"destination_account": beneficiary["Account_Number"]},
                error_code="beneficiary_not_active",
            )

        balance = money(owner["Balance_SAR"])
        if amount > balance:
            return tool_result(
                status="failed",
                summary="The available balance is not enough for this transfer.",
                data={
                    "requested_amount_sar": str(amount),
                    "available_balance_sar": str(balance),
                },
                error_code="insufficient_funds",
            )

        daily_limit = money(owner["Daily_Spend_Limit_SAR"])
        already_spent = spent_today(connection, owner["uuid"])
        if already_spent + amount > daily_limit:
            return tool_result(
                status="failed",
                summary="This transfer would exceed the daily spend limit.",
                data={
                    "requested_amount_sar": str(amount),
                    "spent_today_sar": str(already_spent),
                    "daily_limit_sar": str(daily_limit),
                },
                error_code="daily_limit_exceeded",
            )

        receiver = find_user_by_account_number(connection, beneficiary["Account_Number"])
        if receiver is None or receiver["status"] != "active":
            return tool_result(
                status="failed",
                summary="The destination bank account is no longer available.",
                data={"destination_account": beneficiary["Account_Number"]},
                error_code="destination_account_unavailable",
            )

        reference = next_reference(connection, "transfer")
        now = timestamp()
        sender_balance_after = balance - amount
        receiver_balance_after = money(receiver["Balance_SAR"]) + amount

        connection.execute(
            "UPDATE users SET Balance_SAR = %s, updatedAt = %s WHERE uuid = %s",
            (float(sender_balance_after), now, owner["uuid"]),
        )
        connection.execute(
            "UPDATE users SET Balance_SAR = %s, updatedAt = %s WHERE uuid = %s",
            (float(receiver_balance_after), now, receiver["uuid"]),
        )
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (%s, %s, %s, 'debit', 'transfer_out', %s, %s, %s, %s, 'حوالات', %s, %s, %s)",
            (
                str(uuid4()),
                owner["uuid"],
                owner["Account_Number"],
                float(amount),
                beneficiary["Full_Name"],
                beneficiary["Account_Number"],
                f"حوالة إلى {beneficiary['Short_Name']}",
                float(sender_balance_after),
                reference,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (%s, %s, %s, 'credit', 'transfer_in', %s, %s, %s, %s, 'حوالات', %s, %s, %s)",
            (
                str(uuid4()),
                receiver["uuid"],
                receiver["Account_Number"],
                float(amount),
                owner["Full_Name_Ar"],
                owner["Account_Number"],
                f"حوالة واردة من {owner['Full_Name_Ar']}",
                float(receiver_balance_after),
                reference,
                now,
            ),
        )

        return tool_result(
            status="completed",
            summary=(
                f"Transferred {amount} SAR to {beneficiary['Short_Name']} "
                f"({beneficiary['Account_Number']})."
            ),
            data={
                "reference": reference,
                "amount_sar": str(amount),
                "destination": {
                    "short_name": beneficiary["Short_Name"],
                    "account_number": beneficiary["Account_Number"],
                },
                "new_balance_sar": str(sender_balance_after),
                "executed_at": now,
            },
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


TOOL: BaseTool = StructuredTool.from_function(
    coroutine=transfer_between_accounts,
    name="transfer_between_accounts",
    description=(
        "Transfer money from the authenticated user's account to an activated beneficiary "
        "after confirmation. The destination must already be active in the benefit list, and "
        "the amount must be covered by the balance and the daily spend limit."
    ),
    args_schema=TransferBetweenAccountsArgs,
)
