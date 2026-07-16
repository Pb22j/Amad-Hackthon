"""``transfer_between_accounts`` — move money to a saved Nafi beneficiary.

The transfer only completes when every database rule passes: the destination
must be saved in the owner's beneficiary list, the beneficiary must still map
to a bank account, the balance must cover the amount, and the owner's daily
spend limit must not be exceeded. Both ledger entries and both balances are
written in one atomic database transaction, and a completed transfer returns
an authoritative receipt.
"""

from __future__ import annotations

from decimal import Decimal
import math
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field, field_validator

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
    resolve_beneficiary,
    run_in_bank_db,
    spent_today,
    timestamp,
    tool_result,
    update_account_balance,
)


class TransferBetweenAccountsArgs(BankToolArgs):
    destination_account: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Destination Nafi IBAN or the saved beneficiary short/full name, "
            "exactly as the user stated it."
        ),
    )
    # Keep the provider-facing schema to a plain JSON number. Some
    # grammar-constrained tool providers reject numeric range keywords before
    # the tool can run, so enforce the same limits with a Pydantic validator.
    amount: float = Field(
        description="Amount to transfer in SAR.",
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0 or value > 9_999_999_999:
            raise ValueError("amount must be positive and no more than 9,999,999,999 SAR")
        return value


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
    resolution = resolve_beneficiary(connection, owner["uuid"], destination_account)
    beneficiary = resolution.match
    if beneficiary is None:
        if resolution.candidates:
            candidates = [
                {
                    "full_name": candidate["Full_Name"],
                    "full_name_en": candidate["full_name_en"],
                    "short_name": candidate["Short_Name"],
                    "nafi_iban": candidate["nafi_iban"],
                }
                for candidate in resolution.candidates
            ]
            return tool_result(
                status="failed",
                summary="More than one saved beneficiary closely matches the destination.",
                data={
                    "destination_account": destination_account,
                    "candidates": candidates,
                },
                error_code="beneficiary_ambiguous",
            )
        return tool_result(
            status="failed",
            summary=(
                "The destination is not in the beneficiary list. It must be added and "
                "added with add_benefit before transferring."
            ),
            data={"destination_account": destination_account},
            error_code="beneficiary_not_found",
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
    if receiver is None:
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
            data={
                "resolved_destination": {
                    "full_name": validation[1]["Full_Name"],
                    "full_name_en": validation[1]["full_name_en"],
                    "short_name": validation[1]["Short_Name"],
                    "nafi_iban": validation[1]["nafi_iban"],
                }
            },
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
        beneficiary = find_beneficiary(connection, owner["uuid"], destination_account)
        if beneficiary is None:
            return tool_result(
                status="failed",
                summary=(
                    "The destination is not in the beneficiary list. It must be added and "
                    "added with add_benefit before transferring."
                ),
                data={"destination_account": destination_account},
                error_code="beneficiary_not_found",
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
        if receiver is None:
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

        update_account_balance(connection, owner, sender_balance_after)
        update_account_balance(connection, receiver, receiver_balance_after)
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
                f"({beneficiary['nafi_iban']})."
            ),
            data={
                "reference": reference,
                "amount_sar": str(amount),
                "destination": {
                    "short_name": beneficiary["Short_Name"],
                    "nafi_iban": beneficiary["nafi_iban"],
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
        "Transfer money from the authenticated user's account to a saved Nafi beneficiary "
        "immediately in hackathon demo mode. The destination must already be in the benefit list, and "
        "the amount must be covered by the balance and the daily spend limit. When the user "
        "provides both a destination and amount, call this capability directly: its preflight "
        "is the authority on whether the beneficiary exists. Never ask the user to confirm "
        "whether a named beneficiary is saved before calling it. Preserve the destination text "
        "as the user stated it when possible. The database resolves the saved Nafi beneficiary "
        "to their current primary bank account only when executing the transfer."
    ),
    args_schema=TransferBetweenAccountsArgs,
)
