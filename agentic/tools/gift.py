"""``send_gift`` — send a money gift with a dedication message.

The sender picks a recipient from their active beneficiary list, an amount,
and a gift message. The amount moves atomically from sender to recipient, and
the recipient's ledger entry carries the dedication along with the sender's
full name — so the gift shows up in their transactions and monthly report as
"هدية من <الاسم الكامل>: <الرسالة>".

Rules: the recipient must be an active beneficiary, the amount must be above
zero and covered by the sender's balance, and the action requires
confirmation and returns a receipt. Gift debits count toward the same daily
spend limit as every other outgoing financial action.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from typing import Any
from uuid import uuid4

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import Field

from agentic.tools.bank_db import (
    BankToolArgs,
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


class SendGiftArgs(BankToolArgs):
    recipient: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "Gift recipient: the saved beneficiary short name or account number, "
            "exactly as the user stated it."
        ),
    )
    # Declared as float so the JSON schema is a plain number (see
    # transfer_between_accounts for the grammar-compatibility rationale).
    amount: float = Field(
        gt=0,
        le=9_999_999_999,
        description="Gift amount in SAR; must be above 0.0.",
    )
    gift_message: str = Field(
        min_length=1,
        max_length=500,
        description="The dedication message delivered to the recipient with the gift.",
    )


async def send_gift(
    recipient: str, amount: float | Decimal, gift_message: str
) -> dict[str, Any]:
    """Send a gift to an active beneficiary with the dedication message."""

    username, _ = owner_identity()
    amount = money(amount)
    message = gift_message.strip()

    def work(connection: sqlite3.Connection) -> dict[str, Any]:
        # The schema already enforces gt=0; this guards direct calls too.
        if amount <= 0:
            return tool_result(
                status="failed",
                summary="The gift amount must be above 0.0 SAR.",
                data={"requested_amount_sar": str(amount)},
                error_code="invalid_amount",
            )

        sender = find_user_by_username(connection, username)
        if sender is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        if sender["status"] != "active":
            return tool_result(
                status="failed",
                summary="The account is not active, so it cannot send gifts.",
                data={},
                error_code="source_account_inactive",
            )

        beneficiary = find_beneficiary(connection, sender["uuid"], recipient)
        if beneficiary is None:
            return tool_result(
                status="failed",
                summary=(
                    "The gift recipient is not in the beneficiary list. They must be "
                    "added and activated with add_benefit before receiving a gift."
                ),
                data={"recipient": recipient},
                error_code="beneficiary_not_found",
            )
        if beneficiary["status"] != "active":
            return tool_result(
                status="failed",
                summary="The recipient exists but is not activated for transfers.",
                data={"recipient": beneficiary["Short_Name"]},
                error_code="beneficiary_not_active",
            )

        balance = money(sender["Balance_SAR"])
        if amount > balance:
            return tool_result(
                status="failed",
                summary="The available balance is not enough to send this gift.",
                data={
                    "requested_amount_sar": str(amount),
                    "available_balance_sar": str(balance),
                },
                error_code="insufficient_funds",
            )
        daily_limit = money(sender["Daily_Spend_Limit_SAR"])
        already_spent = spent_today(connection, sender["uuid"])
        if already_spent + amount > daily_limit:
            return tool_result(
                status="failed",
                summary="This gift would exceed the daily spend limit.",
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
                summary="The recipient's bank account is no longer available.",
                data={"recipient": beneficiary["Short_Name"]},
                error_code="destination_account_unavailable",
            )

        reference = next_reference(connection, "gift")
        now = timestamp()
        sender_name = sender["Full_Name_Ar"]
        sender_balance_after = balance - amount
        receiver_balance_after = money(receiver["Balance_SAR"]) + amount
        connection.execute(
            "UPDATE users SET Balance_SAR = ?, updatedAt = ? WHERE uuid = ?",
            (float(sender_balance_after), now, sender["uuid"]),
        )
        connection.execute(
            "UPDATE users SET Balance_SAR = ?, updatedAt = ? WHERE uuid = ?",
            (float(receiver_balance_after), now, receiver["uuid"]),
        )
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (?, ?, ?, 'debit', 'gift_out', ?, ?, ?, ?, 'هدايا', ?, ?, ?)",
            (
                str(uuid4()),
                sender["uuid"],
                sender["Account_Number"],
                float(amount),
                beneficiary["Full_Name"],
                beneficiary["Account_Number"],
                f"هدية إلى {beneficiary['Short_Name']}: {message}",
                float(sender_balance_after),
                reference,
                now,
            ),
        )
        # The recipient's entry names the sender in full and carries the
        # dedication, so the gift reads complete in their statement.
        connection.execute(
            "INSERT INTO transactions"
            " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
            "  Counterparty_Name, Counterparty_Account, Description, Category,"
            "  Balance_After_SAR, Reference, createdAt)"
            " VALUES (?, ?, ?, 'credit', 'gift_in', ?, ?, ?, ?, 'هدايا', ?, ?, ?)",
            (
                str(uuid4()),
                receiver["uuid"],
                receiver["Account_Number"],
                float(amount),
                sender_name,
                sender["Account_Number"],
                f"هدية من {sender_name}: {message}",
                float(receiver_balance_after),
                reference,
                now,
            ),
        )

        return tool_result(
            status="completed",
            summary=(
                f"Gift of {amount} SAR sent to {beneficiary['Short_Name']} with the "
                f"dedication message, signed by {sender_name}."
            ),
            data={
                "reference": reference,
                "amount_sar": str(amount),
                "gift_message": message,
                "from": sender_name,
                "to": {
                    "short_name": beneficiary["Short_Name"],
                    "full_name": beneficiary["Full_Name"],
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
    coroutine=send_gift,
    name="send_gift",
    description=(
        "Send a money gift (هدية) to an activated beneficiary after confirmation. "
        "Takes the recipient, the amount (must be above 0.0 SAR), and a dedication "
        "message; the amount is deducted from the sender and delivered to the "
        "recipient together with the message and the sender's full name."
    ),
    args_schema=SendGiftArgs,
)
