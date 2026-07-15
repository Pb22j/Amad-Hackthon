"""Unit tests for the PostgreSQL-backed bank tools using the private test adapter."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from agentic.tools.add_benefit import add_benefit
from agentic.tools.accounts import get_balance, search_transactions
from agentic.tools.analyze_finances import analyze_finances
from agentic.tools.fatoorah import list_fatoorahs, pay_fatoorah
from agentic.tools.gift import send_gift
from agentic.tools.investments import buy_investment, get_portfolio, sell_investment
from agentic.tools.metadata import ToolResult
from agentic.tools.monthly_report import monthly_report
from agentic.tools.qatta import (
    cancel_qatta,
    create_qatta,
    list_qatta_bills,
    pay_qatta_bill,
)
from agentic.tools.transfer_between_accounts import transfer_between_accounts
from agentic.tools.runtime_identity import bind_tool_identity

# Seeded fixture accounts (see agentic/tools/bank_db.py).
LATIFA_ACCOUNT = "SA98000068368508501525"  # active, pre-registered beneficiary
MOHAMMED_ACCOUNT = "SA0320000005556667772222"  # active, not yet a beneficiary
SAUD_ACCOUNT = "SA91000032763205429515"  # inactive bank customer
OWN_ACCOUNT = "SA4405000068201234567890"  # the evaluation user's own account


ROOT = Path(__file__).resolve().parents[2]


def _database_url(base_url: str, database_name: str) -> str:
    parsed = urlsplit(base_url.replace("postgresql+psycopg://", "postgresql://", 1))
    return urlunsplit(parsed._replace(path=f"/{database_name}"))


@pytest.fixture(scope="session")
def bank_template_database() -> tuple[str, str]:
    base_url = os.getenv(
        "TEST_POSTGRES_URL",
        "postgresql://amad:development-only-password@localhost:55432/amad",
    )
    template_name = f"amad_bank_template_{uuid4().hex[:8]}"
    admin_url = _database_url(base_url, "postgres")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(template_name)))
    template_url = _database_url(base_url, template_name)
    environment = os.environ | {
        "DATABASE_URL": template_url.replace("postgresql://", "postgresql+psycopg://", 1)
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "scripts/seed_postgres.py", "--database-url", template_url],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    yield admin_url, template_name
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(template_name))
        )


@pytest.fixture(autouse=True)
def bank_database(bank_template_database, monkeypatch):
    admin_url, template_name = bank_template_database
    database_name = f"amad_bank_test_{uuid4().hex[:12]}"
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(database_name), sql.Identifier(template_name)
            )
        )
    database_url = _database_url(admin_url, database_name)
    monkeypatch.setenv("BANK_DATABASE_URL", database_url)
    try:
        yield
    finally:
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )


def _validated(result: dict) -> ToolResult:
    """Every tool response must satisfy the shared result envelope."""

    return ToolResult.model_validate(result)


async def test_balance_and_transaction_search_are_bank_backed():
    balance = _validated(await get_balance())
    assert balance.status == "completed"
    assert balance.data["balance_sar"] == "25431.50"
    assert "*" in balance.data["masked_account_number"]

    transactions = _validated(await search_transactions(query="راتب", limit=5))
    assert transactions.status == "completed"
    assert transactions.data["transactions"]
    assert all("راتب" in item["description"] for item in transactions.data["transactions"])


async def test_request_scoped_bank_identity_is_concurrency_safe():
    async def read_as(user_id: str) -> ToolResult:
        with bind_tool_identity(user_id=user_id, tenant_id="evaluation-tenant"):
            return _validated(await get_balance())

    evaluation, admin = await asyncio.gather(
        read_as("evaluation-user"),
        read_as("admin"),
    )
    assert evaluation.user_id == "evaluation-user"
    assert admin.user_id == "admin"
    assert evaluation.data["balance_sar"] != admin.data["balance_sar"]


async def test_portfolio_buy_and_sell_update_bank_balance_and_holdings():
    before = _validated(await get_portfolio())
    aramco = next(item for item in before.data["holdings"] if item["symbol"] == "ARAMCO")
    assert aramco["quantity"] == "20"

    purchase = _validated(await buy_investment(symbol="SABIC", quantity=2))
    assert purchase.status == "completed"
    assert purchase.receipt_id
    assert purchase.data["total_sar"] == "122.40"

    sale = _validated(await sell_investment(symbol="SABIC", quantity=1))
    assert sale.status == "completed"
    assert sale.data["remaining_quantity"] == "1"

    after = _validated(await get_portfolio())
    sabic = next(item for item in after.data["holdings"] if item["symbol"] == "SABIC")
    assert sabic["quantity"] == "1"


async def test_investment_trade_rejects_unknown_symbols_and_excess_sales():
    unknown = _validated(await buy_investment(symbol="UNKNOWN", quantity=1))
    assert unknown.error_code == "investment_not_found"
    excess = _validated(await sell_investment(symbol="ARAMCO", quantity=999))
    assert excess.error_code == "insufficient_holdings"
    over_limit = _validated(await buy_investment(symbol="SABIC", quantity=100))
    assert over_limit.error_code == "daily_limit_exceeded"


@pytest.mark.parametrize("alias", ["ARAMCO", "2222", "Saudi Aramco", "أرامكو", "ارامكو"])
async def test_investment_accepts_arabic_name_and_tadawul_aliases(alias):
    result = _validated(await buy_investment(symbol=alias, quantity=1))
    assert result.status == "completed"
    assert result.data["symbol"] == "ARAMCO"


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


async def test_analyze_finances_computes_deterministic_insights():
    result = _validated(await analyze_finances())
    assert result.status == "completed"
    data = result.data
    assert data["period_months"] == 3
    assert len(data["monthly"]) == 3

    # The oldest analyzed month is fully seeded: salary 15,500 + 750 received,
    # and 6,591.15 spent across the fixed activity template.
    oldest = data["monthly"][0]
    assert oldest["income_sar"] == "16250.00"
    assert oldest["spent_sar"] == "6591.15"

    assert data["top_counterparties"][0]["name"] == "شركة الفيصلية العقارية"
    recurring_names = {item["name"] for item in data["recurring_commitments"]}
    assert "شركة الفيصلية العقارية" in recurring_names
    assert "راتب" in data["category_trends"]

    projection = data["current_month_projection"]
    assert projection["balance_covers_projection"] is True
    assert projection["days_elapsed"] >= 1

    assert data["unpaid_fatoorahs"]["count"] == 3
    assert data["unpaid_fatoorahs"]["total_sar"] == "563.85"
    flag_codes = {flag["code"] for flag in data["flags"]}
    assert "unpaid_bills_due_soon" in flag_codes


async def test_analyze_finances_focus_category_and_single_month():
    result = _validated(await analyze_finances(months=1, focus_category="فواتير"))
    assert result.status == "completed"
    assert len(result.data["monthly"]) == 1
    focus = result.data["focus_category"]
    assert focus["category"] == "فواتير"
    assert all(
        item["counterparty"] in {"الشركة السعودية للكهرباء", "STC"}
        for item in focus["transactions"]
    )


async def test_list_fatoorahs_shows_only_the_users_bills():
    result = _validated(await list_fatoorahs())
    assert result.status == "completed"
    billers = {item["biller"] for item in result.data["fatoorahs"]}
    assert billers == {"الشركة السعودية للكهرباء", "شركة المياه الوطنية", "STC"}
    assert result.data["unpaid_total_sar"] == "563.85"  # 348.60 + 86.25 + 129.00
    assert all(item["bill_number"].isdigit() for item in result.data["fatoorahs"])


async def test_pay_fatoorah_by_last_four_digits_shows_in_monthly_report():
    result = _validated(await pay_fatoorah(last_four_digits="1234"))
    assert result.status == "completed"
    assert result.receipt_id and result.receipt_id.startswith("receipt-")
    assert result.data["biller"] == "الشركة السعودية للكهرباء"
    assert result.data["bill_status"] == "مدفوعة"
    assert result.data["new_balance_sar"] == "25082.90"  # 25431.50 - 348.60

    again = _validated(await pay_fatoorah(last_four_digits="1234"))
    assert again.error_code == "already_paid"

    report = _validated(await monthly_report())
    entry = next(item for item in report.data["transactions"] if item["type"] == "fatoorah_payment")
    assert entry["description"] == "سداد فاتورة الشركة السعودية للكهرباء رقم 30012345671234"
    assert entry["category"] == "فواتير"


async def test_pay_fatoorah_rejects_unknown_digits_and_insufficient_funds(monkeypatch):
    unknown = _validated(await pay_fatoorah(last_four_digits="0000"))
    assert unknown.error_code == "fatoorah_not_found"

    invalid = _validated(await pay_fatoorah(last_four_digits="12x4"))
    assert invalid.error_code == "invalid_bill_digits"

    # وليد's seeded traffic-fines bill (20,000) exceeds his 15,000 balance.
    monkeypatch.setenv("BANK_TOOL_USER_ID", "waleed")
    broke = _validated(await pay_fatoorah(last_four_digits="4444"))
    assert broke.error_code == "insufficient_funds"


async def test_pay_fatoorah_counts_toward_the_daily_spend_limit():
    _validated(await pay_fatoorah(last_four_digits="1234"))
    transfer = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("4950.00")
        )
    )
    assert transfer.error_code == "daily_limit_exceeded"


async def test_send_gift_delivers_message_with_sender_full_name(monkeypatch):
    result = _validated(
        await send_gift(
            recipient="لطيفة",
            amount=Decimal("250.00"),
            gift_message="مبروك التخرج يا لطيفة",
        )
    )
    assert result.status == "completed"
    assert result.receipt_id and result.receipt_id.startswith("receipt-")
    assert result.data["from"] == "أحمد فهد العتيبي"
    assert result.data["gift_message"] == "مبروك التخرج يا لطيفة"
    assert result.data["new_balance_sar"] == "25181.50"

    # The recipient's statement shows the gift with the dedication and the
    # sender's full name.
    monkeypatch.setenv("BANK_TOOL_USER_ID", "user_69491")
    report = _validated(await monthly_report())
    gift_entry = next(item for item in report.data["transactions"] if item["type"] == "gift_in")
    assert gift_entry["counterparty"] == "أحمد فهد العتيبي"
    assert gift_entry["description"] == "هدية من أحمد فهد العتيبي: مبروك التخرج يا لطيفة"
    assert report.data["current_balance_sar"] == "32966.00"  # 32716 + 250


async def test_send_gift_rejects_non_beneficiary_and_insufficient_funds():
    stranger = _validated(
        await send_gift(recipient="محمد", amount=Decimal("50.00"), gift_message="عيدية")
    )
    assert stranger.error_code == "beneficiary_not_found"

    broke = _validated(
        await send_gift(recipient="لطيفة", amount=Decimal("999999.00"), gift_message="هدية")
    )
    assert broke.error_code == "insufficient_funds"


async def test_send_gift_enforces_the_daily_spend_limit():
    gift = _validated(
        await send_gift(recipient="لطيفة", amount=Decimal("7000.00"), gift_message="هدية زواج")
    )
    assert gift.error_code == "daily_limit_exceeded"


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


async def test_qatta_rounding_preserves_the_exact_requested_total():
    _validated(
        await add_benefit(
            full_name_of_benefit_account="محمد ناصر القحطاني",
            benefit_account_number=MOHAMMED_ACCOUNT,
            short_name="محمد",
        )
    )
    result = _validated(
        await create_qatta(
            qatta_name="قطة دقيقة",
            total_amount=100,
            participants=["لطيفة", "محمد"],
        )
    )
    shares = [Decimal(item["share_sar"]) for item in result.data["qatta"]["participants"]]
    assert sum(shares) == Decimal("100.00")
    assert max(shares) - min(shares) <= Decimal("0.01")


async def test_create_qatta_rejects_share_beyond_balance():
    # 10,000,000 / 2 = 5,000,000 per person — far beyond the 25,431.50 balance.
    broke = _validated(
        await create_qatta(qatta_name="قطة عشاء", total_amount=10_000_000, participants=["لطيفة"])
    )
    assert broke.status == "failed"
    assert broke.error_code == "insufficient_funds"


async def test_qatta_payments_count_toward_the_transfer_daily_limit():
    _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    transfer = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_ACCOUNT, amount=Decimal("4950.00")
        )
    )
    assert transfer.error_code == "daily_limit_exceeded"


async def test_qatta_creation_enforces_the_daily_spend_limit():
    result = _validated(
        await create_qatta(qatta_name="قطة رحلة", total_amount=30_000, participants=["لطيفة"])
    )
    assert result.error_code == "daily_limit_exceeded"


async def test_create_qatta_rejects_non_beneficiary_participant():
    result = _validated(
        await create_qatta(qatta_name="قطة", total_amount=100, participants=["محمد"])
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
        item for item in created.data["qattas_i_created"] if item["name"] == "قطة عشاء الجمعة"
    )
    # The pot holds the creator's seeded share plus the freshly paid bill.
    assert qatta["pot_collected_sar"] == "200.00"
    assert qatta["paid_out_sar"] == "0.00"
    paid = {item["full_name"]: item["status"] for item in qatta["participants"]}
    assert paid["أحمد فهد العتيبي"] == "تم الدفع"
    assert paid["لطيفة العنزي"] == "غير مدفوعة"
