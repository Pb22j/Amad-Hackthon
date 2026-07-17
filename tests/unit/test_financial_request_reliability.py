from __future__ import annotations

from agentic.policy.engine import PolicyEngine
from agentic.policy.models import Intent, IntentClassification, RiskLevel
from agentic.tools.accounts import _transaction_matches
from agentic.tools.guard import _clarification_copy, _preflight_failure


def _row(**overrides):
    row = {
        "direction": "debit",
        "Transaction_Type": "transfer_out",
        "Amount_SAR": "125.50",
        "Counterparty_Name": "Ali Hassan",
        "Counterparty_Account": "SA0001",
        "Description": "حوالة إلى علي",
        "Category": "حوالات",
        "Reference": "TRX-123",
        "createdAt": "2026-07-17 09:30:00",
    }
    row.update(overrides)
    return row


def test_transaction_search_matches_bilingual_terms_and_distinctive_values():
    row = _row()

    assert _transaction_matches(row, "transfer to Ali")
    assert _transaction_matches(row, "حوالة إلى علي")
    assert _transaction_matches(row, "125.50")
    assert _transaction_matches(row, "TRX-123")
    assert not _transaction_matches(row, "Khalid")


def test_generic_recent_transaction_wording_does_not_filter_everything_out():
    assert _transaction_matches(_row(), "show my latest transactions")
    assert _transaction_matches(_row(), "اعرض آخر العمليات")
    assert _transaction_matches(_row(), "show my last 5 transactions")
    assert _transaction_matches(_row(), "اعرض آخر ٥ عمليات")


def test_read_only_financial_intents_are_consistently_medium_risk(app_config):
    policy = PolicyEngine(app_config.policies)

    for intent in (
        Intent.ACCOUNT_INFORMATION,
        Intent.TRANSACTION_SEARCH,
        Intent.BENEFICIARY_INFORMATION,
        Intent.BILL_INFORMATION,
        Intent.INVESTMENT_RESEARCH,
    ):
        assessment = policy.assess_intent(
            IntentClassification(intent=intent, confidence=1, rationale_code="read_only")
        )
        assert assessment.level == RiskLevel.MEDIUM
        assert not assessment.requires_confirmation


def test_english_transfer_clarifications_are_specific():
    assert _clarification_copy("amount", "Transfer money to Ali")[0] == (
        "What amount should be used?"
    )
    assert _clarification_copy("destination_account", "Transfer 100 SAR")[0] == (
        "What saved beneficiary name or Nafi IBAN should receive the transfer?"
    )


def test_preflight_failure_is_safe_localized_and_has_no_receipt():
    class Auth:
        user_id = "user-1"
        tenant_id = "tenant-1"

    class Context:
        auth = Auth()
        original_request = "حوّل 100 ريال إلى علي"

    result = _preflight_failure(Context(), operation="transfer")

    assert result.status == "failed"
    assert "لم تُنفذ" in result.summary
    assert result.error_code == "transfer_preflight_unavailable"
    assert result.receipt_id is None
