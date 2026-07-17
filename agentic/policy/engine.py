"""Deterministic request screening and financial intent risk assessment."""

from __future__ import annotations

from dataclasses import dataclass

from agentic.config.loader import PoliciesConfig
from agentic.policy.injection_signals import InjectionSignals, detect_injection_signals
from agentic.policy.models import Intent, IntentClassification, RiskAssessment, RiskLevel
from agentic.tools.metadata import ToolMetadata


HIGH_RISK_INTENTS = {
    Intent.IDLE_CASH_TRANSFER,
    Intent.MONEY_TRANSFER,
    Intent.WALLET_FUNDING,
    Intent.SAVED_BENEFICIARY_TRANSFER,
    Intent.GIFT_TRANSFER,
    Intent.BILL_PAYMENT,
    Intent.BENEFICIARY_MANAGEMENT,
    Intent.INVESTMENT_BUY,
    Intent.INVESTMENT_SELL,
    Intent.PORTFOLIO_MODIFICATION,
}

PROHIBITED_INTENTS = {
    Intent.ACCESS_OTHER_USER,
    Intent.CREDENTIAL_THEFT,
    Intent.FRAUD,
    Intent.MONEY_LAUNDERING,
    Intent.MARKET_MANIPULATION,
    Intent.COMPLIANCE_BYPASS,
}


@dataclass(frozen=True, slots=True)
class RequestPolicyDecision:
    allowed: bool
    reason_code: str
    signals: InjectionSignals


class PolicyEngine:
    def __init__(self, config: PoliciesConfig) -> None:
        self.config = config

    def screen_request(self, text: str) -> RequestPolicyDecision:
        signals = detect_injection_signals(text)
        # Injection signals alone do not block legitimate requests. The agent remains contained
        # by deterministic authorization and tool guards even if this detector misses an attack.
        credential_signal = any("credential_request" in code for code in signals.codes)
        identity_signal = any("identity_override" in code for code in signals.codes)
        bulk_exfiltration_signal = "bulk_data_exfiltration" in signals.codes
        if credential_signal and self.config.security.reject_credential_requests:
            return RequestPolicyDecision(False, "credential_request", signals)
        if identity_signal and self.config.security.reject_cross_user_requests:
            return RequestPolicyDecision(False, "cross_user_request", signals)
        if bulk_exfiltration_signal and self.config.security.reject_cross_user_requests:
            return RequestPolicyDecision(False, "bulk_data_exfiltration", signals)
        return RequestPolicyDecision(True, "allowed", signals)

    def assess_intent(self, classification: IntentClassification) -> RiskAssessment:
        intents = set(classification.all_intents)
        prohibited = intents & PROHIBITED_INTENTS
        if prohibited:
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                reason_codes=tuple(sorted(intent.value for intent in prohibited)),
                requires_confirmation=False,
                contains_sensitive_data=True,
            )
        if intents & HIGH_RISK_INTENTS:
            return RiskAssessment(
                level=RiskLevel.HIGH,
                reason_codes=("financial_action",),
                requires_confirmation=True,
            )
        if intents & {
            Intent.ACCOUNT_INFORMATION,
            Intent.TRANSACTION_SEARCH,
            Intent.BENEFICIARY_INFORMATION,
            Intent.BILL_INFORMATION,
            Intent.FINANCIAL_ADVICE,
            Intent.INVESTMENT_RESEARCH,
        }:
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                reason_codes=("sensitive_financial_data",),
                contains_sensitive_data=True,
            )
        return RiskAssessment(level=RiskLevel.LOW)

    def intent_allowed(self, intent: Intent) -> bool:
        return intent not in PROHIBITED_INTENTS and intent.value not in self.config.security.blocked_intents

    def classification_allowed(self, classification: IntentClassification) -> bool:
        """Reject a compound request when any requested intent is prohibited."""

        return all(self.intent_allowed(intent) for intent in classification.all_intents)

    def advisor_tool_allowed(self, metadata: ToolMetadata) -> bool:
        """Return whether a capability can cross the advisory read-only boundary."""

        advisor = self.config.financial_advisor
        return (
            advisor.advisory_only
            and metadata.risk.value in advisor.allowed_tool_risks
            and not metadata.requires_confirmation
            and not metadata.requires_receipt
        )
