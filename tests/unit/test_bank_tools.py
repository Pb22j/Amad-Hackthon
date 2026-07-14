"""Unit tests for the SQLite-backed bank tools."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agentic.tools.add_benefit import add_benefit
from agentic.tools.bank_db import reset_bank_state
from agentic.tools.metadata import ToolResult
from agentic.tools.monthly_report import monthly_report
from agentic.tools.qatta import (
    cancel_qatta,
    create_qatta,
    list_qatta_bills,
    pay_qatta_bill,
)
from agentic.tools.transfer_between_accounts import transfer_between_accounts

# Seeded fixture accounts (see agentic/tools/bank_db.py).
LATIFA_ACCOUNT = "SA98000068368508501525"  # active, pre-registered beneficiary
MOHAMMED_ACCOUNT = "SA0320000005556667772222"  # active, not yet a beneficiary
SAUD_ACCOUNT = "SA91000032763205429515"  # inactive bank customer
OWN_ACCOUNT = "SA4405000068201234567890"  # the evaluation user's own account


@pytest.fixture(autouse=True)
def bank_database(tmp_path, monkeypatch):
    monkeypatch.setenv("BANK_DB_PATH", str(tmp_path / "bank.db"))
    reset_bank_state()
    yield
    reset_bank_state()


def _validated(result: dict) -> ToolResult:
    """Every tool response must satisfy the shared result envelope."""

    return ToolResult.model_validate(result)


async def test_add_benefit_activates_verified_account():
    result = _validated(
        await add_benefit(
            full_name_of_benefit_account="محمد ناصر القحطاني",
            benefit_account_number=MOHAMMED_ACCOUNT,
            short_name="محمد",
        )
    )
    assert result.status == "completed"
    assert result.operation_id
    assert result.user_id == "evaluation-user"
    assert result.data["beneficiary"]["status"] == "active"


async def test_add_benefit_rejects_duplicate_beneficiary():
    result = _validated(
        await add_benefit(
            full_name_of_benefit_account="لطيفة العنزي",
            benefit_account_number=LATIFA_ACCOUNT,
            short_name="لطيفة",
        )
    )
    assert result.status == "failed"
    assert result.error_code == "beneficiary_already_exists"


async def test_add_benefit_rejects_unknown_account_number():
    result = _validated(
        await add_benefit(
            full_name_of_benefit_account="غير موجود",
            benefit_account_number="SA0000000000000000000000",
            short_name="مجهول",
        )
    )
    assert result.status == "failed"
    assert result.error_code == "account_not_found"


async def test_add_benefit_rejects_own_and_inactive_accounts():
    own = _validated(
        await add_benefit(
            full_name_of_benefit_account="أحمد فهد العتيبي",
            benefit_account_number=OWN_ACCOUNT,
            short_name="حسابي",
        )
    )
    assert own.error_code == "cannot_add_own_account"

    inactive = _validated(
        await add_benefit(
            full_name_of_benefit_account="سعود العنزي",
            benefit_account_number=SAUD_ACCOUNT,
            short_name="سعود",
        )
    )
    assert inactive.error_code == "account_inactive"


async def test_transfer_completes_with_receipt_and_updates_balance():
    result = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("250.00")
        )
    )
    assert result.status == "completed"
    assert result.receipt_id and result.receipt_id.startswith("receipt-")
    assert result.data["new_balance_sar"] == "25181.50"

    report = _validated(await monthly_report())
    references = [item["reference"] for item in report.data["transactions"]]
    assert result.operation_id in references


async def test_transfer_accepts_saved_short_name():
    result = _validated(
        await transfer_between_accounts(destination_account="لطيفة", amount=Decimal("10.00"))
    )
    assert result.status == "completed"
    assert result.data["destination"]["account_number"] == LATIFA_ACCOUNT


async def test_transfer_rejects_unregistered_destination():
    result = _validated(
        await transfer_between_accounts(
            destination_account=MOHAMMED_ACCOUNT, amount=Decimal("50.00")
        )
    )
    assert result.status == "failed"
    assert result.error_code == "beneficiary_not_found"
    assert result.receipt_id is None


async def test_transfer_rejects_insufficient_funds():
    result = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("999999.00")
        )
    )
    assert result.status == "failed"
    assert result.error_code == "insufficient_funds"


async def test_transfer_enforces_daily_spend_limit():
    first = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("4900.00")
        )
    )
    assert first.status == "completed"

    second = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("200.00")
        )
    )
    assert second.status == "failed"
    assert second.error_code == "daily_limit_exceeded"


async def test_monthly_report_summarizes_current_month():
    result = _validated(await monthly_report())
    assert result.status == "completed"
    data = result.data
    assert Decimal(data["total_received_sar"]) >= Decimal("15500.00")  # seeded salary
    assert Decimal(data["total_paid_sar"]) > 0
    assert data["transaction_count"] == len(data["transactions"])
    assert "راتب" in data["categories"]


async def test_monthly_report_for_empty_month_is_valid():
    result = _validated(await monthly_report(month="2020-01"))
    assert result.status == "completed"
    assert result.data["total_paid_sar"] == "0.00"
    assert result.data["total_received_sar"] == "0.00"
    assert result.data["transactions"] == []


async def test_create_qatta_splits_equally_and_deducts_creator_share():
    _validated(
        await add_benefit(
            full_name_of_benefit_account="محمد ناصر القحطاني",
            benefit_account_number=MOHAMMED_ACCOUNT,
            short_name="محمد",
        )
    )
    result = _validated(
        await create_qatta(
            qatta_name="قطة كشتة",
            total_amount=100,
            participants=["لطيفة", "محمد"],
        )
    )
    assert result.status == "completed"
    assert result.receipt_id  # the creator's share deduction is a real action
    qatta = result.data["qatta"]
    # Creator counts in the split: 100 / 3 people, paid into the pot for real.
    assert qatta["share_per_person_sar"] == "33.33"
    assert qatta["pot_collected_sar"] == "33.33"
    assert qatta["creator_new_balance_sar"] == "25398.17"  # 25431.50 - 33.33
    statuses = {item["full_name"]: item["status"] for item in qatta["participants"]}
    assert statuses["أحمد فهد العتيبي"] == "تم الدفع"  # creator paid into the pot
    assert statuses["لطيفة العنزي"] == "غير مدفوعة"
    assert statuses["محمد ناصر القحطاني"] == "غير مدفوعة"


async def test_create_qatta_rejects_share_beyond_balance():
    # 10,000,000 / 2 = 5,000,000 per person — far beyond the 25,431.50 balance.
    broke = _validated(
        await create_qatta(
            qatta_name="قطة عشاء", total_amount=10_000_000, participants=["لطيفة"]
        )
    )
    assert broke.status == "failed"
    assert broke.error_code == "insufficient_funds"


async def test_qatta_payments_do_not_consume_the_transfer_daily_limit():
    # Pay a 100 SAR qatta bill, then transfer 4,950 SAR: if the qatta payment
    # counted toward the 5,000 daily limit this transfer would be rejected
    # (100 + 4,950 > 5,000). It must succeed.
    _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    transfer = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("4950.00")
        )
    )
    assert transfer.status == "completed"

    # Regular transfers still cap at the limit on their own.
    over = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("100.00")
        )
    )
    assert over.error_code == "daily_limit_exceeded"


async def test_qatta_is_exempt_from_the_daily_spend_limit():
    # 30,000 / 2 = 15,000 per person — over the 5,000 daily limit, but qatta
    # payments deliberately bypass it; only the balance matters.
    result = _validated(
        await create_qatta(
            qatta_name="قطة رحلة", total_amount=30_000, participants=["لطيفة"]
        )
    )
    assert result.status == "completed"
    assert result.data["qatta"]["creator_new_balance_sar"] == "10431.50"


async def test_create_qatta_rejects_non_beneficiary_participant():
    result = _validated(
        await create_qatta(
            qatta_name="قطة", total_amount=100, participants=["محمد"]
        )
    )
    assert result.error_code == "participant_not_beneficiary"


async def test_add_benefit_rejects_duplicate_short_name():
    result = _validated(
        await add_benefit(
            full_name_of_benefit_account="محمد ناصر القحطاني",
            benefit_account_number=MOHAMMED_ACCOUNT,
            short_name="لطيفة",  # already used by the seeded beneficiary
        )
    )
    assert result.status == "failed"
    assert result.error_code == "short_name_already_used"


async def test_pay_qatta_bill_fills_pot_and_pays_out_creator(monkeypatch):
    # The seeded "قطة عشاء الجمعة" (creator: admin) has two unpaid 100 SAR bills.
    result = _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    assert result.status == "completed"
    assert result.receipt_id and result.receipt_id.startswith("receipt-")
    assert result.data["bill_status"] == "تم الدفع"
    assert result.data["paid_to"] == "وعاء القطة"
    assert result.data["qatta_status"] == "open"
    assert result.data["new_balance_sar"] == "25331.50"
    assert "payout" not in result.data

    again = _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    assert again.error_code == "already_paid"

    monkeypatch.setenv("BANK_TOOL_USER_ID", "user_69491")
    last = _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    assert last.status == "completed"
    assert last.data["qatta_status"] == "completed"
    # The full pot (3 x 100) pays out to the creator only on completion.
    assert last.data["payout"]["payout_sar"] == "300.00"
    assert last.data["payout"]["paid_to_creator"] == "عبدالإله سعيد المسفر"

    monkeypatch.setenv("BANK_TOOL_USER_ID", "admin")
    report = _validated(await monthly_report())
    assert report.data["current_balance_sar"] == "150300.00"  # 150000 + pot


async def test_cancel_qatta_refunds_everyone_who_paid(monkeypatch):
    # evaluation-user pays their 100 SAR bill into the seeded qatta pot.
    _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))

    # Only the creator (admin) can cancel.
    not_creator = _validated(await cancel_qatta(qatta_name="قطة عشاء الجمعة"))
    assert not_creator.status == "failed"
    assert not_creator.error_code == "only_creator_can_cancel"

    monkeypatch.setenv("BANK_TOOL_USER_ID", "admin")
    result = _validated(await cancel_qatta(qatta_name="قطة عشاء الجمعة"))
    assert result.status == "completed"
    assert result.receipt_id
    # Pot held admin's seeded share + evaluation-user's payment.
    assert result.data["total_refunded_sar"] == "200.00"
    refunded = {item["full_name"]: item["refunded_sar"] for item in result.data["refunds"]}
    assert refunded["عبدالإله سعيد المسفر"] == "100.00"
    assert refunded["أحمد فهد العتيبي"] == "100.00"

    # The payer got their money back and the qatta is gone.
    monkeypatch.setenv("BANK_TOOL_USER_ID", "evaluation-user")
    report = _validated(await monthly_report())
    assert report.data["current_balance_sar"] == "25431.50"  # restored
    bills = _validated(await list_qatta_bills())
    assert bills.data["bills_i_owe"] == []


async def test_cancel_qatta_rejects_unknown_and_completed(monkeypatch):
    unknown = _validated(await cancel_qatta(qatta_name="قطة غير موجودة"))
    assert unknown.error_code == "qatta_not_found"

    # Complete the seeded qatta, then the creator tries to cancel it.
    _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    monkeypatch.setenv("BANK_TOOL_USER_ID", "user_69491")
    _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    monkeypatch.setenv("BANK_TOOL_USER_ID", "admin")
    completed = _validated(await cancel_qatta(qatta_name="قطة عشاء الجمعة"))
    assert completed.error_code == "qatta_already_completed"


async def test_pay_qatta_bill_rejects_unknown_name():
    result = _validated(await pay_qatta_bill(qatta_name="قطة غير موجودة"))
    assert result.error_code == "qatta_bill_not_found"


async def test_list_qatta_bills_shows_owed_and_created(monkeypatch):
    owed = _validated(await list_qatta_bills())
    assert owed.status == "completed"
    assert any(
        bill["qatta_name"] == "قطة عشاء الجمعة" and bill["status"] == "غير مدفوعة"
        for bill in owed.data["bills_i_owe"]
    )

    _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    monkeypatch.setenv("BANK_TOOL_USER_ID", "admin")
    created = _validated(await list_qatta_bills())
    qatta = next(
        item
        for item in created.data["qattas_i_created"]
        if item["name"] == "قطة عشاء الجمعة"
    )
    # The pot holds the creator's seeded share plus the freshly paid bill.
    assert qatta["pot_collected_sar"] == "200.00"
    assert qatta["paid_out_sar"] == "0.00"
    paid = {
        item["full_name"]: item["status"] for item in qatta["participants"]
    }
    assert paid["أحمد فهد العتيبي"] == "تم الدفع"
    assert paid["لطيفة العنزي"] == "غير مدفوعة"
