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

from agentic.tools.add_benefit import add_benefit, list_beneficiaries
from agentic.tools.accounts import get_balance, search_transactions
from agentic.tools.analyze_finances import analyze_finances
from agentic.tools.fatoorah import list_fatoorahs, pay_fatoorah
from agentic.tools.gift import send_gift
from agentic.tools.idle_cash import (
    analyze_idle_cash,
    preflight_transfer_idle_cash_to_savings,
    transfer_idle_cash_to_savings,
)
from agentic.tools.investments import buy_investment, get_portfolio, sell_investment
from agentic.tools.metadata import ToolResult
from agentic.tools.monthly_report import monthly_report
from agentic.tools.qatta import (
    cancel_qatta,
    create_qatta,
    list_qatta_bills,
    pay_qatta_bill,
)
from agentic.tools.transfer_between_accounts import (
    TransferBetweenAccountsArgs,
    preflight_transfer_between_accounts,
    transfer_between_accounts,
)
from agentic.tools.wallet_funding import (
    FundNafiWalletArgs,
    fund_nafi_wallet,
    preflight_fund_nafi_wallet,
    source_account_is_grounded,
)
from agentic.tools.runtime_identity import bind_tool_identity, bind_tool_operation
from VoiceAssistant_Nafea.backend.app.dashboard import (
    DashboardStore,
    DepositAccountNotFound,
    DepositInsufficientFunds,
    DepositRequestConflict,
)

# Seeded Nafi identities (see scripts/seed_postgres.py).
EVALUATION_NAFI_IBAN = "SA9900000000000000000001"
MOHAMMED_NAFI_IBAN = "SA9900000000000000000004"
LATIFA_NAFI_IBAN = "SA9900000000000000000006"
SAUD_NAFI_IBAN = "SA9900000000000000000007"


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


def test_transfer_provider_schema_uses_plain_number_with_server_side_limits():
    amount_schema = TransferBetweenAccountsArgs.model_json_schema()["properties"]["amount"]
    assert amount_schema["type"] == "number"
    assert "exclusiveMinimum" not in amount_schema
    assert "maximum" not in amount_schema

    with pytest.raises(ValueError):
        TransferBetweenAccountsArgs(destination_account="Ahmed", amount=0)
    with pytest.raises(ValueError):
        TransferBetweenAccountsArgs(destination_account="Ahmed", amount=float("inf"))


def test_wallet_funding_provider_schema_uses_plain_number_with_server_side_limits():
    amount_schema = FundNafiWalletArgs.model_json_schema()["properties"]["amount"]
    assert amount_schema["type"] == "number"
    assert "exclusiveMinimum" not in amount_schema
    assert "maximum" not in amount_schema

    with pytest.raises(ValueError):
        FundNafiWalletArgs(source_account="Savings", amount=0)
    with pytest.raises(ValueError):
        FundNafiWalletArgs(source_account="Savings", amount=float("inf"))


async def test_balance_and_transaction_search_are_bank_backed():
    balance = _validated(await get_balance())
    assert balance.status == "completed"
    assert balance.data["balance_sar"] == "25431.50"
    assert balance.data["nafi_balance_sar"] == "25431.50"
    assert balance.data["spendable_balance_sar"] == "25431.50"
    assert balance.data["nafi_liquid_savings_balance_sar"] == "0.00"
    assert balance.data["total_balance_sar"] == "29631.50"
    assert len(balance.data["accounts"]) == 2
    assert "*" in balance.data["masked_account_number"]

    transactions = _validated(await search_transactions(query="راتب", limit=5))
    assert transactions.status == "completed"
    assert transactions.data["transactions"]
    assert all("راتب" in item["description"] for item in transactions.data["transactions"])


async def test_idle_cash_analysis_persists_explicit_wallet_only_recommendation():
    result = _validated(await analyze_idle_cash())

    assert result.status == "completed"
    assert result.data["history_sufficient"] is True
    assert result.data["methodology"]["analysis_months"] == 3
    assert result.data["methodology"]["emergency_months"] == 3
    assert result.data["linked_bank_accounts_are_read_only"] is True
    assert result.data["no_bank_money_moved"] is True
    assert result.data["wallet_deposit_notice"]
    assert result.data["wallet_deposit_notice_ar"]
    recommended = Decimal(result.data["recommended_wallet_transfer_sar"])
    assert recommended > 0
    assert str(recommended) in result.data["consent_question"]
    assert str(recommended) in result.data["consent_question_ar"]

    with psycopg.connect(os.environ["BANK_DATABASE_URL"]) as connection:
        row = connection.execute(
            """SELECT status, recommended_wallet_transfer_sar,
                      emergency_reserve_target_sar
                 FROM idle_cash_recommendations
                WHERE uuid = %s""",
            (result.data["recommendation_id"],),
        ).fetchone()
    assert row[0] == "active"
    assert row[1] == recommended
    assert row[2] == Decimal(result.data["emergency_reserve_target_sar"])


async def test_idle_cash_analysis_conservatively_imputes_one_zero_month():
    with psycopg.connect(os.environ["BANK_DATABASE_URL"]) as connection:
        connection.execute(
            """DELETE FROM transactions
                WHERE user_uuid = (
                    SELECT uuid FROM users WHERE username = 'evaluation-user'
                )
                  AND createdat >= date_trunc('month', CURRENT_TIMESTAMP) - interval '1 month'
                  AND createdat < date_trunc('month', CURRENT_TIMESTAMP)"""
        )

    result = _validated(await analyze_idle_cash())

    assert result.status == "completed"
    assert result.data["history_sufficient"] is True
    assert result.data["months_with_payment_data"] == 2
    monthly = result.data["monthly_cash_flow"]
    imputed = [month for month in monthly if month["imputed_for_reserve"]]
    observed = [
        Decimal(month["projected_full_month_spend_sar"])
        for month in monthly
        if not month["imputed_for_reserve"]
    ]
    assert len(imputed) == 1
    assert Decimal(imputed[0]["reserve_month_spend_sar"]) == max(observed)


async def test_idle_cash_transfer_moves_only_nafi_wallet_money_and_writes_paired_ledger():
    analysis = _validated(await analyze_idle_cash())
    amount = Decimal(analysis.data["recommended_wallet_transfer_sar"])
    assert amount > 0

    preview = _validated(await preflight_transfer_idle_cash_to_savings())
    assert preview.status == "completed"
    assert preview.data["confirmation_arguments"]["amount_sar"] == str(amount)
    assert preview.data["bank_accounts_are_read_only"] is True

    database_url = os.environ["BANK_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        bank_before = connection.execute(
            """SELECT a.uuid::text, a.balance_sar FROM bank_accounts a
                 JOIN users u ON u.uuid = a.user_uuid
                WHERE u.username = 'evaluation-user' ORDER BY a.uuid"""
        ).fetchall()
        wallet_before, savings_before = connection.execute(
            """SELECT u.nafi_balance, s.balance_sar FROM users u
                 JOIN nafi_savings_accounts s ON s.user_uuid = u.uuid
                WHERE u.username = 'evaluation-user' AND s.account_type = 'liquid'"""
        ).fetchone()

    result = _validated(await transfer_idle_cash_to_savings())
    assert result.status == "completed"
    assert result.receipt_id
    assert result.data["amount_sar"] == str(amount)
    assert result.data["linked_bank_accounts_changed"] is False

    with psycopg.connect(database_url) as connection:
        bank_after = connection.execute(
            """SELECT a.uuid::text, a.balance_sar FROM bank_accounts a
                 JOIN users u ON u.uuid = a.user_uuid
                WHERE u.username = 'evaluation-user' ORDER BY a.uuid"""
        ).fetchall()
        wallet_after, savings_after = connection.execute(
            """SELECT u.nafi_balance, s.balance_sar FROM users u
                 JOIN nafi_savings_accounts s ON s.user_uuid = u.uuid
                WHERE u.username = 'evaluation-user' AND s.account_type = 'liquid'"""
        ).fetchone()
        ledger = connection.execute(
            "SELECT direction, transaction_type FROM transactions WHERE reference = %s",
            (result.data["reference"],),
        ).fetchall()
        recommendation_status = connection.execute(
            "SELECT status FROM idle_cash_recommendations WHERE uuid = %s",
            (analysis.data["recommendation_id"],),
        ).fetchone()[0]

    assert bank_after == bank_before
    assert wallet_after == wallet_before - amount
    assert savings_after == savings_before + amount
    assert set(ledger) == {
        ("debit", "nafi_liquid_savings_debit"),
        ("credit", "nafi_liquid_savings_credit"),
    }
    assert recommendation_status == "executed"


async def test_idle_cash_action_requires_a_prior_active_recommendation():
    result = _validated(await preflight_transfer_idle_cash_to_savings())

    assert result.status == "failed"
    assert result.error_code == "idle_cash_recommendation_required"
    assert result.data["bank_accounts_are_read_only"] is True


async def test_provider_operation_result_reconciles_after_execution_recording_crash():
    database_url = os.environ["BANK_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        before = connection.execute(
            "SELECT nafi_balance FROM users WHERE username = 'evaluation-user'"
        ).fetchone()[0]

    with bind_tool_identity(user_id="evaluation-user", tenant_id="evaluation-tenant"):
        with bind_tool_operation(
            idempotency_key="reconciliation-test-key",
            tool_name="transfer_between_accounts",
        ):
            first = _validated(
                await transfer_between_accounts(
                    destination_account="لطيفة", amount=Decimal("10.00")
                )
            )
        # Simulate a new worker retrying after the provider committed but the
        # application tool_execution row was never completed.
        with bind_tool_operation(
            idempotency_key="reconciliation-test-key",
            tool_name="transfer_between_accounts",
        ):
            recovered = _validated(
                await transfer_between_accounts(
                    destination_account="لطيفة", amount=Decimal("10.00")
                )
            )

    assert recovered == first
    with psycopg.connect(database_url) as connection:
        after = connection.execute(
            "SELECT nafi_balance FROM users WHERE username = 'evaluation-user'"
        ).fetchone()[0]
        result_count = connection.execute(
            "SELECT count(*) FROM financial_operation_results"
            " WHERE idempotency_key = 'reconciliation-test-key'"
        ).fetchone()[0]
    assert after == before - Decimal("10.00")
    assert result_count == 1


async def test_agentic_wallet_funding_preflights_and_moves_only_selected_bank_money():
    database_url = os.environ["BANK_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        before_rows = connection.execute(
            """
            SELECT a.uuid::text, a.account_type, a.balance_sar, u.nafi_balance
              FROM users u JOIN bank_accounts a ON a.user_uuid = u.uuid
             WHERE u.username = 'evaluation-user'
             ORDER BY a.is_primary DESC
            """
        ).fetchall()
    primary_id, _, primary_before, wallet_before = before_rows[0]
    savings_id, _, savings_before, _ = before_rows[1]

    preview = _validated(await preflight_fund_nafi_wallet("Savings", Decimal("75.25")))
    result = _validated(await fund_nafi_wallet("Savings", Decimal("75.25")))

    assert preview.status == "completed"
    assert preview.data["resolved_source"]["account_type"] == "Savings"
    assert result.status == "completed"
    assert result.receipt_id
    assert result.data["source_bank_balance_sar"] == "4124.75"
    assert result.data["new_nafi_balance_sar"] == "25506.75"
    with psycopg.connect(database_url) as connection:
        balances = dict(
            connection.execute(
                "SELECT uuid::text, balance_sar FROM bank_accounts WHERE uuid IN (%s, %s)",
                (primary_id, savings_id),
            ).fetchall()
        )
        wallet_after = connection.execute(
            "SELECT nafi_balance FROM users WHERE username = 'evaluation-user'"
        ).fetchone()[0]
        ledger = connection.execute(
            "SELECT transaction_type FROM transactions WHERE reference = %s",
            (result.data["reference"],),
        ).fetchall()
    assert balances[primary_id] == primary_before
    assert balances[savings_id] == savings_before - Decimal("75.25")
    assert wallet_after == wallet_before + Decimal("75.25")
    assert {row[0] for row in ledger} == {"nafi_top_up_source", "nafi_top_up"}


async def test_agentic_wallet_funding_rejects_ambiguous_or_insufficient_sources():
    ambiguous = _validated(await preflight_fund_nafi_wallet("مصرف", Decimal("1.00")))
    insufficient = _validated(await preflight_fund_nafi_wallet("Savings", Decimal("999999")))

    assert ambiguous.status == "failed"
    assert ambiguous.error_code == "source_account_ambiguous"
    assert len(ambiguous.data["candidates"]) == 2
    assert insufficient.status == "failed"
    assert insufficient.error_code == "insufficient_bank_funds"


@pytest.mark.parametrize(
    "spoken_alias",
    ("bank alahli", "Al Ahli", "Ahli", "الاهلي", "الأهلي", "اهلي", "البنك الاهلي"),
)
async def test_wallet_funding_resolves_spoken_alahli_alias_from_owned_accounts(
    spoken_alias: str,
):
    with bind_tool_identity(user_id="admin", tenant_id="evaluation-tenant"):
        balance = _validated(await get_balance(account=spoken_alias))
        preview = _validated(
            await preflight_fund_nafi_wallet(spoken_alias, Decimal("1.00"))
        )

    assert balance.status == "completed"
    assert balance.data["bank_name"] == "البنك الأهلي السعودي"
    assert preview.status == "completed"
    assert preview.data["resolved_source"]["bank_name"] == "Saudi National Bank"


async def test_wallet_funding_asks_when_spoken_generic_bank_reference_matches_multiple_accounts():
    preview = _validated(
        await preflight_fund_nafi_wallet("bank", Decimal("1.00"))
    )

    assert preview.status == "failed"
    assert preview.error_code == "source_account_ambiguous"
    assert len(preview.data["candidates"]) == 2


async def test_wallet_funding_binds_canonical_primary_to_spoken_owned_bank_alias():
    with bind_tool_identity(user_id="admin", tenant_id="evaluation-tenant"):
        grounded = await source_account_is_grounded(
            "primary",
            ("هلا نافع بالله ضف 700 ريال لمحفظتي من حسابي في الاهلي",),
        )
        unrelated = await source_account_is_grounded(
            "primary",
            ("أودع 700 ريال من مصرف الراجحي",),
        )

    assert grounded is True
    assert unrelated is False


async def test_wallet_funding_automatically_grounds_a_sole_owned_account():
    with bind_tool_identity(user_id="admin", tenant_id="evaluation-tenant"):
        grounded = await source_account_is_grounded(
            "primary",
            ("أودع 700 ريال في محفظة نافع",),
        )

    assert grounded is True

    with bind_tool_identity(user_id="admin", tenant_id="evaluation-tenant"):
        named_unlinked_bank = await source_account_is_grounded(
            "primary",
            ("Deposit 700 SAR into Nafi from Rajhi",),
        )

    assert named_unlinked_bank is False


async def test_wallet_funding_does_not_default_when_user_owns_multiple_accounts():
    with bind_tool_identity(user_id="evaluation-user", tenant_id="evaluation-tenant"):
        grounded = await source_account_is_grounded(
            "primary",
            ("Deposit 700 SAR into my Nafi wallet",),
        )

    assert grounded is False


def test_dashboard_deposit_moves_only_selected_bank_funds_into_nafi_wallet():
    database_url = os.environ["BANK_DATABASE_URL"]
    store = DashboardStore(database_url)
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """SELECT a.uuid::text, a.account_type, a.balance_sar, u.nafi_balance
                 FROM users u JOIN bank_accounts a ON a.user_uuid=u.uuid
                WHERE u.username='evaluation-user' ORDER BY a.is_primary DESC"""
        ).fetchall()
    primary_id, _, primary_before, wallet_before = rows[0]
    savings_id, _, savings_before, _ = rows[1]
    request_id = str(uuid4())

    result = store.deposit_to_wallet(
        user_id="evaluation-user",
        tenant_id="evaluation-tenant",
        source_account_id=savings_id,
        amount=Decimal("75.25"),
        request_id=request_id,
    )
    replay = store.deposit_to_wallet(
        user_id="evaluation-user",
        tenant_id="evaluation-tenant",
        source_account_id=savings_id,
        amount=Decimal("75.25"),
        request_id=request_id,
    )

    assert result["source_bank_balance_sar"] == "4124.75"
    assert result["nafi_balance_sar"] == "25506.75"
    assert replay["idempotent_replay"] is True
    with psycopg.connect(database_url) as connection:
        balances = dict(
            connection.execute(
                "SELECT uuid::text, balance_sar FROM bank_accounts WHERE uuid IN (%s, %s)",
                (primary_id, savings_id),
            ).fetchall()
        )
        wallet_after = connection.execute(
            "SELECT nafi_balance FROM users WHERE username='evaluation-user'"
        ).fetchone()[0]
        ledger = connection.execute(
            "SELECT transaction_type FROM transactions WHERE reference=%s",
            (result["reference"],),
        ).fetchall()
    assert balances[primary_id] == primary_before
    assert balances[savings_id] == savings_before - Decimal("75.25")
    assert wallet_after == wallet_before + Decimal("75.25")
    assert {row[0] for row in ledger} == {"nafi_top_up_source", "nafi_top_up"}

    with pytest.raises(DepositRequestConflict):
        store.deposit_to_wallet(
            user_id="evaluation-user",
            tenant_id="evaluation-tenant",
            source_account_id=savings_id,
            amount=Decimal("80.00"),
            request_id=request_id,
        )
    with pytest.raises(DepositInsufficientFunds):
        store.deposit_to_wallet(
            user_id="evaluation-user",
            tenant_id="evaluation-tenant",
            source_account_id=savings_id,
            amount=Decimal("999999.00"),
            request_id=str(uuid4()),
        )
    with psycopg.connect(database_url) as connection:
        admin_account_id = connection.execute(
            """SELECT a.uuid::text FROM users u JOIN bank_accounts a ON a.user_uuid=u.uuid
                WHERE u.username='admin' AND a.is_primary"""
        ).fetchone()[0]
    with pytest.raises(DepositAccountNotFound):
        store.deposit_to_wallet(
            user_id="evaluation-user",
            tenant_id="evaluation-tenant",
            source_account_id=admin_account_id,
            amount=Decimal("1.00"),
            request_id=str(uuid4()),
        )


async def test_balance_resolves_approximate_account_names_and_reports_ambiguity():
    savings = _validated(await get_balance(account="savin"))
    assert savings.status == "completed"
    assert savings.data["account_type"] == "Savings"
    assert savings.data["balance_sar"] == "4200.00"

    ambiguous = _validated(await get_balance(account="مصرف"))
    assert ambiguous.status == "failed"
    assert ambiguous.error_code == "account_ambiguous"
    assert len(ambiguous.data["candidates"]) == 2


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
            nafi_iban=MOHAMMED_NAFI_IBAN,
            short_name="محمد",
        )
    )
    assert result.status == "completed"
    assert result.operation_id
    assert result.user_id == "evaluation-user"
    assert result.data["beneficiary"]["nafi_iban"] == MOHAMMED_NAFI_IBAN
    assert result.data["beneficiary"]["full_name"] == "محمد ناصر القحطاني"


async def test_list_beneficiaries_returns_authoritative_active_entries():
    result = _validated(await list_beneficiaries())

    assert result.status == "completed"
    assert result.data["count"] == len(result.data["beneficiaries"])
    assert result.data["count"] > 0
    assert any(item["nafi_iban"] == LATIFA_NAFI_IBAN for item in result.data["beneficiaries"])


async def test_add_benefit_rejects_existing_beneficiary_by_nafi_identity():
    result = _validated(
        await add_benefit(
            nafi_iban=LATIFA_NAFI_IBAN,
            short_name="لطيفة",
        )
    )

    assert result.status == "failed"
    assert result.error_code == "beneficiary_already_exists"


async def test_add_benefit_rejects_duplicate_beneficiary():
    result = _validated(
        await add_benefit(
            nafi_iban=LATIFA_NAFI_IBAN,
            short_name="لطيفة",
        )
    )
    assert result.status == "failed"
    assert result.error_code == "beneficiary_already_exists"


async def test_add_benefit_rejects_unknown_nafi_iban():
    result = _validated(
        await add_benefit(
            nafi_iban="SA0000000000000000000000",
            short_name="مجهول",
        )
    )
    assert result.status == "failed"
    assert result.error_code == "nafi_iban_not_found"


async def test_add_benefit_rejects_own_and_accepts_another_nafi_user():
    own = _validated(
        await add_benefit(
            nafi_iban=EVALUATION_NAFI_IBAN,
            short_name="حسابي",
        )
    )
    assert own.error_code == "cannot_add_own_account"

    added = _validated(
        await add_benefit(
            nafi_iban=SAUD_NAFI_IBAN,
            short_name="سعود",
        )
    )
    assert added.status == "completed"


async def test_transfer_completes_with_receipt_and_updates_balance():
    database_url = os.environ["BANK_DATABASE_URL"]
    with psycopg.connect(database_url) as connection:
        balances_before = {
            username: (bank_balance, wallet_balance)
            for username, bank_balance, wallet_balance in connection.execute(
                """SELECT u.username::text, a.balance_sar, u.nafi_balance
                 FROM users u JOIN bank_accounts a ON a.user_uuid=u.uuid AND a.is_primary
                WHERE u.username IN ('evaluation-user', 'latifa')"""
            ).fetchall()
        }

    result = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_NAFI_IBAN, amount=Decimal("250.00")
        )
    )
    assert result.status == "completed"
    assert result.receipt_id and result.receipt_id.startswith("receipt-")
    assert result.data["new_balance_sar"] == "25181.50"
    assert result.data["new_nafi_balance_sar"] == "25181.50"

    with psycopg.connect(database_url) as connection:
        balances_after = {
            username: (bank_balance, wallet_balance)
            for username, bank_balance, wallet_balance in connection.execute(
                """SELECT u.username::text, a.balance_sar, u.nafi_balance
                 FROM users u JOIN bank_accounts a ON a.user_uuid=u.uuid AND a.is_primary
                WHERE u.username IN ('evaluation-user', 'latifa')"""
            ).fetchall()
        }
    assert balances_after["evaluation-user"][0] == balances_before["evaluation-user"][0]
    assert balances_after["latifa"][0] == balances_before["latifa"][0]
    assert balances_after["evaluation-user"][1] == (
        balances_before["evaluation-user"][1] - Decimal("250.00")
    )
    assert balances_after["latifa"][1] == (
        balances_before["latifa"][1] + Decimal("250.00")
    )

    report = _validated(await monthly_report())
    references = [item["reference"] for item in report.data["transactions"]]
    assert result.operation_id in references


async def test_transfer_accepts_saved_short_name():
    result = _validated(
        await transfer_between_accounts(destination_account="لطيفة", amount=Decimal("10.00"))
    )
    assert result.status == "completed"
    assert result.data["destination"]["nafi_iban"] == LATIFA_NAFI_IBAN


@pytest.mark.parametrize("destination", ["سعود", "لسعود", "سعوود", "Saud", "Soud"])
async def test_transfer_searches_partial_and_misspelled_beneficiary_names(destination):
    added = _validated(
        await add_benefit(
            nafi_iban=SAUD_NAFI_IBAN,
            short_name="سعود عبدالله العنزي",
        )
    )
    assert added.status == "completed"

    result = _validated(
        await preflight_transfer_between_accounts(
            destination_account=destination,
            amount=Decimal("10.00"),
        )
    )

    assert result.status == "completed"
    assert result.data["resolved_destination"]["full_name"] == "سعود عبدالله العنزي"
    assert result.data["resolved_destination"]["nafi_iban"] == SAUD_NAFI_IBAN


async def test_transfer_returns_candidates_instead_of_guessing_ambiguous_partial_name():
    saud = _validated(
        await add_benefit(
            nafi_iban=SAUD_NAFI_IBAN,
            short_name="سعود عبدالله",
        )
    )
    mohammed = _validated(
        await add_benefit(
            nafi_iban=MOHAMMED_NAFI_IBAN,
            short_name="سعود محمد",
        )
    )
    assert saud.status == mohammed.status == "completed"

    result = _validated(
        await preflight_transfer_between_accounts(
            destination_account="سعود",
            amount=Decimal("10.00"),
        )
    )

    assert result.status == "failed"
    assert result.error_code == "beneficiary_ambiguous"
    assert {candidate["short_name"] for candidate in result.data["candidates"]} == {
        "سعود عبدالله",
        "سعود محمد",
    }


@pytest.mark.parametrize(
    "destination",
    [
        "لطيفة العنزي",
        "لطيفه العنزي",
        "لطيفة محمد",
        "Latifa",
        "Latifa Mohammed",
        "Latifa Al-Anzi",
        "LATIFA AL ANZI",
    ],
)
async def test_transfer_accepts_saved_full_name_and_arabic_spelling_variants(destination):
    result = _validated(
        await transfer_between_accounts(destination_account=destination, amount=Decimal("10.00"))
    )
    assert result.status == "completed"
    assert result.data["destination"]["nafi_iban"] == LATIFA_NAFI_IBAN


async def test_transfer_rejects_unregistered_destination():
    result = _validated(
        await transfer_between_accounts(
            destination_account=MOHAMMED_NAFI_IBAN, amount=Decimal("50.00")
        )
    )
    assert result.status == "failed"
    assert result.error_code == "beneficiary_not_found"
    assert result.receipt_id is None


async def test_transfer_preflight_rejects_ineligible_action_without_mutation():
    before = _validated(await get_balance())
    result = _validated(
        await preflight_transfer_between_accounts(
            destination_account=MOHAMMED_NAFI_IBAN, amount=Decimal("50.00")
        )
    )
    after = _validated(await get_balance())

    assert result.status == "failed"
    assert result.error_code == "beneficiary_not_found"
    assert result.receipt_id is None
    assert after.data["balance_sar"] == before.data["balance_sar"]


async def test_transfer_preflight_accepts_existing_active_beneficiary():
    result = _validated(
        await preflight_transfer_between_accounts(
            destination_account="لطيفة", amount=Decimal("1.00")
        )
    )

    assert result.status == "completed"
    assert result.receipt_id is None


async def test_transfer_rejects_insufficient_funds():
    result = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_NAFI_IBAN, amount=Decimal("999999.00")
        )
    )
    assert result.status == "failed"
    assert result.error_code == "insufficient_funds"


async def test_transfer_enforces_daily_spend_limit():
    first = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_NAFI_IBAN, amount=Decimal("4900.00")
        )
    )
    assert first.status == "completed"

    second = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_NAFI_IBAN, amount=Decimal("200.00")
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

    # The oldest analyzed month is fully seeded with positive cash flow and
    # internally consistent aggregate arithmetic.
    oldest = data["monthly"][0]
    oldest_income = Decimal(oldest["income_sar"])
    oldest_spent = Decimal(oldest["spent_sar"])
    assert oldest_income > oldest_spent > 0
    assert Decimal(oldest["net_sar"]) == oldest_income - oldest_spent

    assert data["top_counterparties"][0]["name"] == "شركة العقار السكنية"
    recurring_names = {item["name"] for item in data["recurring_commitments"]}
    assert "شركة العقار السكنية" in recurring_names
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


async def test_pay_fatoorah_by_biller_shows_in_monthly_report():
    result = _validated(await pay_fatoorah(biller="الكهرباء"))
    assert result.status == "completed"
    assert result.receipt_id and result.receipt_id.startswith("receipt-")
    assert result.data["biller"] == "الشركة السعودية للكهرباء"
    assert result.data["bill_status"] == "مدفوعة"
    assert result.data["new_balance_sar"] == "25082.90"  # 25431.50 - 348.60

    again = _validated(await pay_fatoorah(biller="الكهرباء"))
    assert again.error_code == "already_paid"

    report = _validated(await monthly_report())
    entry = next(item for item in report.data["transactions"] if item["type"] == "fatoorah_payment")
    assert entry["description"] == "سداد فاتورة الشركة السعودية للكهرباء رقم 30012345671234"
    assert entry["category"] == "فواتير"


async def test_pay_fatoorah_rejects_unknown_biller_and_insufficient_funds(monkeypatch):
    unknown = _validated(await pay_fatoorah(biller="مزود غير موجود"))
    assert unknown.error_code == "fatoorah_not_found"

    invalid = _validated(await pay_fatoorah(biller=" "))
    assert invalid.error_code == "invalid_biller"

    # وليد's seeded traffic-fines bill (20,000) exceeds his 15,000 balance.
    monkeypatch.setenv("BANK_TOOL_USER_ID", "waleed")
    broke = _validated(await pay_fatoorah(biller="المرور"))
    assert broke.error_code == "insufficient_funds"


async def test_pay_fatoorah_counts_toward_the_daily_spend_limit():
    _validated(await pay_fatoorah(biller="الكهرباء"))
    transfer = _validated(
        await transfer_between_accounts(
            destination_account=LATIFA_NAFI_IBAN, amount=Decimal("4950.00")
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
    monkeypatch.setenv("BANK_TOOL_USER_ID", "latifa")
    report = _validated(await monthly_report())
    gift_entry = next(item for item in report.data["transactions"] if item["type"] == "gift_in")
    assert gift_entry["counterparty"] == "أحمد فهد العتيبي"
    assert gift_entry["description"] == "هدية من أحمد فهد العتيبي: مبروك التخرج يا لطيفة"
    assert report.data["current_balance_sar"] == "12750.00"  # 12500 + 250


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
            nafi_iban=MOHAMMED_NAFI_IBAN,
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
    assert statuses["لطيفة محمد العنزي"] == "غير مدفوعة"
    assert statuses["محمد ناصر القحطاني"] == "غير مدفوعة"


async def test_qatta_rounding_preserves_the_exact_requested_total():
    _validated(
        await add_benefit(
            nafi_iban=MOHAMMED_NAFI_IBAN,
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
            destination_account=LATIFA_NAFI_IBAN, amount=Decimal("4950.00")
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
            nafi_iban=MOHAMMED_NAFI_IBAN,
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

    monkeypatch.setenv("BANK_TOOL_USER_ID", "latifa")
    last = _validated(await pay_qatta_bill(qatta_name="قطة عشاء الجمعة"))
    assert last.status == "completed"
    assert last.data["qatta_status"] == "completed"
    # The full pot (3 x 100) pays out to the creator only on completion.
    assert last.data["payout"]["payout_sar"] == "300.00"
    assert last.data["payout"]["paid_to_creator"] == "ماجد عبدالله السبيعي"

    monkeypatch.setenv("BANK_TOOL_USER_ID", "admin")
    report = _validated(await monthly_report())
    assert report.data["current_balance_sar"] == "75300.00"  # 75000 + pot


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
    assert refunded["ماجد عبدالله السبيعي"] == "100.00"
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
    monkeypatch.setenv("BANK_TOOL_USER_ID", "latifa")
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
    assert paid["لطيفة محمد العنزي"] == "غير مدفوعة"
