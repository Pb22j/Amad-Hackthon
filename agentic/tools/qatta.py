"""Qatta (قطة) — create, pay, and track equal bill splits between customers.

A qatta is the Saudi custom of splitting one shared expense equally. The
creator names the qatta (e.g. "قطة عشاء"), states the total, and lists the
participants **by their saved beneficiary short names** — only people who are
active in the creator's beneficiary list can join a qatta.

Money flows through the qatta pot (وعاء القطة):

1. Creation splits the total equally over the participants plus the creator.
   The creator's own share is deducted immediately into the pot — a qatta
   cannot be created if the creator's balance cannot cover their share.
   Qatta payments count toward the payer's daily spend limit.
2. Each participant pays their bill into the pot; their bill becomes
   "تم الدفع". Every deduction is a real ledger entry.
3. When the last bill is paid, the whole pot is transferred to the creator's
   account in one payout and the qatta completes.
4. Only the creator can cancel an open qatta: everyone who paid (including
   the creator) is refunded from the pot, and the qatta is removed. The
   ledger keeps the full payment/refund trail.

Four tools with distinct risk profiles share this module:

- ``create_qatta``       financial action (deducts the creator's share)
- ``pay_qatta_bill``     financial action, requires confirmation and receipt
- ``cancel_qatta``       financial action (refunds the pot), creator only
- ``list_qatta_bills``   sensitive read
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


class CreateQattaArgs(BankToolArgs):
    qatta_name: str = Field(
        min_length=1,
        max_length=100,
        description="Name of the qatta, e.g. قطة عشاء.",
    )
    # Declared as float so the JSON schema is a plain number (see
    # transfer_between_accounts for the grammar-compatibility rationale).
    total_amount: float = Field(
        gt=0,
        le=9_999_999_999,
        description="Total amount in SAR to split equally over all participants.",
    )
    participants: list[str] = Field(
        min_length=1,
        max_length=20,
        description=(
            "The other participants sharing the qatta, each identified by their saved "
            "beneficiary short name. Every participant must already be an active "
            "beneficiary in the creator's benefit list. The creator is included in "
            "the split automatically."
        ),
    )


class PayQattaBillArgs(BankToolArgs):
    qatta_name: str = Field(
        min_length=1,
        max_length=100,
        description="Name of the qatta whose bill the user wants to pay.",
    )


class CancelQattaArgs(BankToolArgs):
    qatta_name: str = Field(
        min_length=1,
        max_length=100,
        description="Name of the open qatta the creator wants to cancel.",
    )


class ListQattaBillsArgs(BankToolArgs):
    pass


def _bill_view(row: BankRow) -> dict[str, Any]:
    return {
        "qatta_name": row["Name"],
        "amount_sar": str(money(row["Amount_SAR"])),
        "status": "تم الدفع" if row["status"] == "paid" else "غير مدفوعة",
        "paid_at": row["paidAt"],
    }


def _insert_transaction(
    connection: BankConnection,
    *,
    user: BankRow,
    direction: str,
    transaction_type: str,
    amount: Decimal,
    counterparty_name: str,
    counterparty_account: str | None,
    description: str,
    balance_after: Decimal,
    reference: str,
    now: str,
) -> None:
    connection.execute(
        "INSERT INTO transactions"
        " (uuid, user_uuid, Account_Number, direction, Transaction_Type, Amount_SAR,"
        "  Counterparty_Name, Counterparty_Account, Description, Category,"
        "  Balance_After_SAR, Reference, createdAt)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'قطة', %s, %s, %s)",
        (
            str(uuid4()),
            user["uuid"],
            user["Account_Number"],
            direction,
            transaction_type,
            float(amount),
            counterparty_name,
            counterparty_account,
            description,
            float(balance_after),
            reference,
            now,
        ),
    )


async def create_qatta(
    qatta_name: str, total_amount: float | Decimal, participants: list[str]
) -> dict[str, Any]:
    """Create a qatta, deducting the creator's own share into the qatta pot."""

    username, _ = owner_identity()
    total = money(total_amount)

    def work(connection: BankConnection) -> dict[str, Any]:
        creator = find_user_by_username(connection, username)
        if creator is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )
        if creator["status"] != "active":
            return tool_result(
                status="failed",
                summary="The account is not active, so it cannot create a qatta.",
                data={},
                error_code="source_account_inactive",
            )

        # Participants come exclusively from the creator's beneficiary list and
        # must be active there — the same trust boundary transfers rely on.
        resolved: dict[str, BankRow] = {}
        for reference in participants:
            beneficiary = find_beneficiary(connection, creator["uuid"], reference)
            if beneficiary is None:
                return tool_result(
                    status="failed",
                    summary=(
                        "A participant is not in the beneficiary list. They must be "
                        "added and activated with add_benefit before joining a qatta."
                    ),
                    data={"participant": reference},
                    error_code="participant_not_beneficiary",
                )
            if beneficiary["status"] != "active":
                return tool_result(
                    status="failed",
                    summary="A participant's beneficiary entry is not activated.",
                    data={"participant": beneficiary["Short_Name"]},
                    error_code="beneficiary_not_active",
                )
            participant = find_user_by_account_number(
                connection, beneficiary["Account_Number"]
            )
            if participant is None or participant["status"] != "active":
                return tool_result(
                    status="failed",
                    summary="A participant's bank account is no longer available.",
                    data={"participant": beneficiary["Short_Name"]},
                    error_code="participant_inactive",
                )
            resolved.setdefault(participant["uuid"], participant)

        resolved.pop(creator["uuid"], None)
        if not resolved:
            return tool_result(
                status="failed",
                summary="A qatta needs at least one participant besides the creator.",
                data={"qatta_name": qatta_name},
                error_code="not_enough_participants",
            )

        # Split in integer halalah so the individual bills always sum exactly
        # to the requested total. Any remainder is distributed deterministically.
        resolved[creator["uuid"]] = creator
        total_halalah = int(total * 100)
        base_halalah, remainder = divmod(total_halalah, len(resolved))
        shares = {
            participant_id: money(
                Decimal(base_halalah + (1 if index < remainder else 0)) / 100
            )
            for index, participant_id in enumerate(resolved)
        }
        share = money(Decimal(base_halalah) / 100)
        creator_share = shares[creator["uuid"]]

        # The creator's own share is paid into the pot right now.
        balance = money(creator["Balance_SAR"])
        if creator_share > balance:
            return tool_result(
                status="failed",
                summary=(
                    "The creator's balance cannot cover their own share, so the "
                    "qatta was not created."
                ),
                data={
                    "creator_share_sar": str(creator_share),
                    "available_balance_sar": str(balance),
                },
                error_code="insufficient_funds",
            )
        daily_limit = money(creator["Daily_Spend_Limit_SAR"])
        already_spent = spent_today(connection, creator["uuid"])
        if already_spent + creator_share > daily_limit:
            return tool_result(
                status="failed",
                summary="The creator's share would exceed the daily spend limit.",
                data={
                    "creator_share_sar": str(creator_share),
                    "spent_today_sar": str(already_spent),
                    "daily_limit_sar": str(daily_limit),
                },
                error_code="daily_limit_exceeded",
            )

        now = timestamp()
        qatta_id = str(uuid4())
        reference = next_reference(connection, "qatta")
        balance_after = balance - creator_share
        connection.execute(
            "UPDATE users SET Balance_SAR = %s, updatedAt = %s WHERE uuid = %s",
            (float(balance_after), now, creator["uuid"]),
        )
        _insert_transaction(
            connection,
            user=creator,
            direction="debit",
            transaction_type="qatta_payment",
            amount=creator_share,
            counterparty_name=f"وعاء {qatta_name.strip()}",
            counterparty_account=None,
            description=f"دفع حصة {qatta_name.strip()} إلى وعاء القطة",
            balance_after=balance_after,
            reference=reference,
            now=now,
        )
        connection.execute(
            "INSERT INTO qattas"
            " (uuid, creator_uuid, Name, Total_Amount_SAR, Share_Amount_SAR, status,"
            "  createdAt, updatedAt)"
            " VALUES (%s, %s, %s, %s, %s, 'open', %s, %s)",
            (qatta_id, creator["uuid"], qatta_name.strip(), float(total), float(share),
             now, now),
        )
        for participant in resolved.values():
            is_creator = participant["uuid"] == creator["uuid"]
            connection.execute(
                "INSERT INTO qatta_bills"
                " (uuid, qatta_uuid, participant_uuid, Amount_SAR, status, paidAt, createdAt)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    str(uuid4()),
                    qatta_id,
                    participant["uuid"],
                    float(shares[participant["uuid"]]),
                    "paid" if is_creator else "unpaid",
                    now if is_creator else None,
                    now,
                ),
            )
        return tool_result(
            status="completed",
            summary=(
                f"Qatta {qatta_name.strip()} created: {total} SAR split over "
                f"{len(resolved)} participants to the nearest halalah. The creator's "
                f"{creator_share} SAR share was paid into the qatta pot."
            ),
            data={
                "qatta": {
                    "name": qatta_name.strip(),
                    "total_sar": str(total),
                    "share_per_person_sar": str(share),
                    "creator_share_sar": str(creator_share),
                    "pot_collected_sar": str(creator_share),
                    "creator_new_balance_sar": str(balance_after),
                    "participants": [
                        {
                            "full_name": row["Full_Name_Ar"],
                            "share_sar": str(shares[row["uuid"]]),
                            "status": (
                                "تم الدفع" if row["uuid"] == creator["uuid"] else "غير مدفوعة"
                            ),
                        }
                        for row in resolved.values()
                    ],
                }
            },
            receipt_id=f"receipt-{reference}",
            operation_id=qatta_id,
        )

    return await run_in_bank_db(work)


async def pay_qatta_bill(qatta_name: str) -> dict[str, Any]:
    """Pay the caller's unpaid qatta bill into the pot; the last payment
    triggers the payout of the whole pot to the creator."""

    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        payer = find_user_by_username(connection, username)
        if payer is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )

        cleaned = qatta_name.strip()
        bills = connection.execute(
            "SELECT qatta_bills.*, qattas.Name, qattas.creator_uuid"
            " FROM qatta_bills JOIN qattas ON qattas.uuid = qatta_bills.qatta_uuid"
            " WHERE qatta_bills.participant_uuid = %s"
            "   AND LOWER(TRIM(qattas.Name)) = LOWER(%s)"
            " ORDER BY qatta_bills.createdAt",
            (payer["uuid"], cleaned),
        ).fetchall()
        unpaid = [bill for bill in bills if bill["status"] == "unpaid"]
        if not unpaid:
            if bills:
                return tool_result(
                    status="failed",
                    summary="This qatta bill is already paid.",
                    data={"qatta_name": cleaned, "status": "تم الدفع"},
                    error_code="already_paid",
                )
            return tool_result(
                status="failed",
                summary="No qatta bill with this name is owed by the user.",
                data={"qatta_name": cleaned},
                error_code="qatta_bill_not_found",
            )
        bill = unpaid[0]
        amount = money(bill["Amount_SAR"])

        balance = money(payer["Balance_SAR"])
        if amount > balance:
            return tool_result(
                status="failed",
                summary="The available balance is not enough to pay this qatta bill.",
                data={
                    "requested_amount_sar": str(amount),
                    "available_balance_sar": str(balance),
                },
                error_code="insufficient_funds",
            )
        daily_limit = money(payer["Daily_Spend_Limit_SAR"])
        already_spent = spent_today(connection, payer["uuid"])
        if already_spent + amount > daily_limit:
            return tool_result(
                status="failed",
                summary="This Qatta payment would exceed the daily spend limit.",
                data={
                    "requested_amount_sar": str(amount),
                    "spent_today_sar": str(already_spent),
                    "daily_limit_sar": str(daily_limit),
                },
                error_code="daily_limit_exceeded",
            )
        creator = connection.execute(
            "SELECT * FROM users WHERE uuid = %s", (bill["creator_uuid"],)
        ).fetchone()
        if creator is None or creator["status"] != "active":
            return tool_result(
                status="failed",
                summary="The qatta creator's account is no longer available.",
                data={"qatta_name": cleaned},
                error_code="destination_account_unavailable",
            )

        reference = next_reference(connection, "qatta")
        now = timestamp()
        payer_balance_after = balance - amount
        connection.execute(
            "UPDATE users SET Balance_SAR = %s, updatedAt = %s WHERE uuid = %s",
            (float(payer_balance_after), now, payer["uuid"]),
        )
        _insert_transaction(
            connection,
            user=payer,
            direction="debit",
            transaction_type="qatta_payment",
            amount=amount,
            counterparty_name=f"وعاء {bill['Name']}",
            counterparty_account=None,
            description=f"دفع فاتورة {bill['Name']} إلى وعاء القطة",
            balance_after=payer_balance_after,
            reference=reference,
            now=now,
        )
        connection.execute(
            "UPDATE qatta_bills SET status = 'paid', paidAt = %s WHERE uuid = %s",
            (now, bill["uuid"]),
        )

        remaining = connection.execute(
            "SELECT COUNT(*) FROM qatta_bills WHERE qatta_uuid = %s AND status = 'unpaid'",
            (bill["qatta_uuid"],),
        ).fetchone()[0]
        payout: dict[str, Any] | None = None
        if remaining == 0:
            # The last bill fills the pot: pay the whole pot out to the creator.
            pot_total = money(
                connection.execute(
                    "SELECT COALESCE(SUM(Amount_SAR), 0) FROM qatta_bills"
                    " WHERE qatta_uuid = %s",
                    (bill["qatta_uuid"],),
                ).fetchone()[0]
            )
            payout_reference = next_reference(connection, "qatta-payout")
            creator_balance_after = money(creator["Balance_SAR"]) + pot_total
            connection.execute(
                "UPDATE users SET Balance_SAR = %s, updatedAt = %s WHERE uuid = %s",
                (float(creator_balance_after), now, creator["uuid"]),
            )
            _insert_transaction(
                connection,
                user=creator,
                direction="credit",
                transaction_type="qatta_payout",
                amount=pot_total,
                counterparty_name=f"وعاء {bill['Name']}",
                counterparty_account=None,
                description=f"تحصيل {bill['Name']} كاملة من وعاء القطة",
                balance_after=creator_balance_after,
                reference=payout_reference,
                now=now,
            )
            connection.execute(
                "UPDATE qattas SET status = 'completed', updatedAt = %s WHERE uuid = %s",
                (now, bill["qatta_uuid"]),
            )
            payout = {
                "payout_sar": str(pot_total),
                "payout_reference": payout_reference,
                "paid_to_creator": creator["Full_Name_Ar"],
            }

        data: dict[str, Any] = {
            "qatta_name": bill["Name"],
            "amount_sar": str(amount),
            "paid_to": "وعاء القطة",
            "bill_status": "تم الدفع",
            "qatta_status": "completed" if remaining == 0 else "open",
            "remaining_unpaid_bills": remaining,
            "new_balance_sar": str(payer_balance_after),
            "reference": reference,
            "executed_at": now,
        }
        if payout:
            data["payout"] = payout
        return tool_result(
            status="completed",
            summary=(
                f"Paid {amount} SAR into the pot of qatta {bill['Name']}."
                + (
                    " All bills are now paid; the pot was transferred to the creator."
                    if remaining == 0
                    else ""
                )
            ),
            data=data,
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


async def cancel_qatta(qatta_name: str) -> dict[str, Any]:
    """Cancel an open qatta — creator only. Refunds every paid share from the
    pot back to its payer and removes the qatta; the ledger keeps the trail."""

    username, _ = owner_identity()

    def work(connection: BankConnection) -> dict[str, Any]:
        owner = find_user_by_username(connection, username)
        if owner is None:
            return tool_result(
                status="failed",
                summary="The authenticated customer profile was not found.",
                data={},
                error_code="customer_not_found",
            )

        cleaned = qatta_name.strip()
        mine = connection.execute(
            "SELECT * FROM qattas WHERE creator_uuid = %s"
            " AND LOWER(TRIM(Name)) = LOWER(%s) ORDER BY createdAt",
            (owner["uuid"], cleaned),
        ).fetchall()
        open_qattas = [row for row in mine if row["status"] == "open"]
        if not open_qattas:
            if mine:
                return tool_result(
                    status="failed",
                    summary="This qatta is already completed, so it cannot be cancelled.",
                    data={"qatta_name": cleaned},
                    error_code="qatta_already_completed",
                )
            someone_elses = connection.execute(
                "SELECT 1 FROM qatta_bills"
                " JOIN qattas ON qattas.uuid = qatta_bills.qatta_uuid"
                " WHERE qatta_bills.participant_uuid = %s"
                "   AND LOWER(TRIM(qattas.Name)) = LOWER(%s)",
                (owner["uuid"], cleaned),
            ).fetchone()
            if someone_elses is not None:
                return tool_result(
                    status="failed",
                    summary="Only the qatta creator can cancel it.",
                    data={"qatta_name": cleaned},
                    error_code="only_creator_can_cancel",
                )
            return tool_result(
                status="failed",
                summary="No open qatta with this name was created by the user.",
                data={"qatta_name": cleaned},
                error_code="qatta_not_found",
            )
        qatta = open_qattas[0]

        now = timestamp()
        reference = next_reference(connection, "qatta-cancel")
        paid_bills = connection.execute(
            "SELECT qatta_bills.*, users.uuid AS payer_uuid"
            " FROM qatta_bills JOIN users ON users.uuid = qatta_bills.participant_uuid"
            " WHERE qatta_bills.qatta_uuid = %s AND qatta_bills.status = 'paid'"
            " ORDER BY qatta_bills.createdAt",
            (qatta["uuid"],),
        ).fetchall()

        refunds: list[dict[str, str]] = []
        total_refunded = Decimal("0.00")
        for bill in paid_bills:
            payer = connection.execute(
                "SELECT * FROM users WHERE uuid = %s", (bill["payer_uuid"],)
            ).fetchone()
            amount = money(bill["Amount_SAR"])
            balance_after = money(payer["Balance_SAR"]) + amount
            connection.execute(
                "UPDATE users SET Balance_SAR = %s, updatedAt = %s WHERE uuid = %s",
                (float(balance_after), now, payer["uuid"]),
            )
            _insert_transaction(
                connection,
                user=payer,
                direction="credit",
                transaction_type="qatta_refund",
                amount=amount,
                counterparty_name=f"وعاء {qatta['Name']}",
                counterparty_account=None,
                description=f"استرداد حصة {qatta['Name']} بعد إلغائها",
                balance_after=balance_after,
                reference=reference,
                now=now,
            )
            refunds.append(
                {"full_name": payer["Full_Name_Ar"], "refunded_sar": str(amount)}
            )
            total_refunded += amount

        connection.execute(
            "DELETE FROM qatta_bills WHERE qatta_uuid = %s", (qatta["uuid"],)
        )
        connection.execute("DELETE FROM qattas WHERE uuid = %s", (qatta["uuid"],))

        return tool_result(
            status="completed",
            summary=(
                f"Qatta {qatta['Name']} was cancelled by its creator; "
                f"{total_refunded} SAR was refunded from the pot to everyone who paid."
            ),
            data={
                "qatta_name": qatta["Name"],
                "total_refunded_sar": str(total_refunded),
                "refunds": refunds,
                "cancelled_at": now,
            },
            receipt_id=f"receipt-{reference}",
            operation_id=reference,
        )

    return await run_in_bank_db(work)


async def list_qatta_bills() -> dict[str, Any]:
    """List the bills the user owes and the qattas the user created."""

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

        owed_rows = connection.execute(
            "SELECT qatta_bills.*, qattas.Name, users.Full_Name_Ar AS creator_name"
            " FROM qatta_bills"
            " JOIN qattas ON qattas.uuid = qatta_bills.qatta_uuid"
            " JOIN users ON users.uuid = qattas.creator_uuid"
            " WHERE qatta_bills.participant_uuid = %s AND qattas.creator_uuid != %s"
            " ORDER BY qatta_bills.createdAt DESC",
            (user["uuid"], user["uuid"]),
        ).fetchall()
        my_bills = [
            {**_bill_view(row), "created_by": row["creator_name"]} for row in owed_rows
        ]

        created_rows = connection.execute(
            "SELECT * FROM qattas WHERE creator_uuid = %s ORDER BY createdAt DESC",
            (user["uuid"],),
        ).fetchall()
        my_qattas = []
        for qatta in created_rows:
            participant_rows = connection.execute(
                "SELECT qatta_bills.*, qattas.Name, users.Full_Name_Ar AS participant_name"
                " FROM qatta_bills"
                " JOIN qattas ON qattas.uuid = qatta_bills.qatta_uuid"
                " JOIN users ON users.uuid = qatta_bills.participant_uuid"
                " WHERE qatta_bills.qatta_uuid = %s"
                " ORDER BY qatta_bills.createdAt",
                (qatta["uuid"],),
            ).fetchall()
            # The pot holds every paid share (including the creator's) until
            # the payout empties it into the creator's account.
            pot = sum(
                (money(row["Amount_SAR"]) for row in participant_rows
                 if row["status"] == "paid"),
                Decimal("0.00"),
            )
            completed = qatta["status"] == "completed"
            my_qattas.append(
                {
                    "name": qatta["Name"],
                    "status": qatta["status"],
                    "total_sar": str(money(qatta["Total_Amount_SAR"])),
                    "share_per_person_sar": str(money(qatta["Share_Amount_SAR"])),
                    "pot_collected_sar": "0.00" if completed else str(pot),
                    "paid_out_sar": str(pot) if completed else "0.00",
                    "participants": [
                        {**_bill_view(row), "full_name": row["participant_name"]}
                        for row in participant_rows
                    ],
                }
            )

        return tool_result(
            status="completed",
            summary=(
                f"Found {len(my_bills)} qatta bills owed and {len(my_qattas)} qattas "
                f"created by the user."
            ),
            data={"bills_i_owe": my_bills, "qattas_i_created": my_qattas},
            operation_id=next_reference(connection, "qatta-list"),
        )

    return await run_in_bank_db(work)


CREATE_QATTA_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=create_qatta,
    name="create_qatta",
    description=(
        "Create a qatta (قطة): split a total amount equally between the creator and "
        "participants chosen by their saved beneficiary short names, after "
        "confirmation. Participants must be active beneficiaries in the creator's "
        "benefit list. The creator's own share is deducted immediately into the qatta "
        "pot, so the creator's balance must cover their share."
    ),
    args_schema=CreateQattaArgs,
)

PAY_QATTA_BILL_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=pay_qatta_bill,
    name="pay_qatta_bill",
    description=(
        "Pay the authenticated user's unpaid qatta bill by name after confirmation. "
        "The share is paid into the qatta pot and the bill becomes paid (تم الدفع); "
        "when the last bill is paid, the whole pot transfers to the qatta creator."
    ),
    args_schema=PayQattaBillArgs,
)

CANCEL_QATTA_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=cancel_qatta,
    name="cancel_qatta",
    description=(
        "Cancel an open qatta by name after confirmation — only its creator can do "
        "this. Every paid share (including the creator's) is refunded from the qatta "
        "pot back to its payer, and the qatta with its bills is removed."
    ),
    args_schema=CancelQattaArgs,
)

LIST_QATTA_BILLS_TOOL: BaseTool = StructuredTool.from_function(
    coroutine=list_qatta_bills,
    name="list_qatta_bills",
    description=(
        "List the authenticated user's qatta bills: what they owe (with payment "
        "status) and the qattas they created (with who paid, the pot balance, and "
        "the payout once completed)."
    ),
    args_schema=ListQattaBillsArgs,
)
