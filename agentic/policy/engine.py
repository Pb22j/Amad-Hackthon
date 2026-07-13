from __future__ import annotations

from dataclasses import dataclass

from agentic.config.loader import PoliciesConfig
from agentic.policy.injection_signals import InjectionSignals, detect_injection_signals
from agentic.policy.models import Intent, IntentClassification, RiskAssessment, RiskLevel


HIGH_RISK_INTENTS = {
    Intent.MONEY_TRANSFER,
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
        if credential_signal and self.config.security.reject_credential_requests:
            return RequestPolicyDecision(False, "credential_request", signals)
        if identity_signal and self.config.security.reject_cross_user_requests:
            return RequestPolicyDecision(False, "cross_user_request", signals)
        return RequestPolicyDecision(True, "allowed", signals)

    def assess_intent(self, classification: IntentClassification) -> RiskAssessment:
        if classification.intent in PROHIBITED_INTENTS:
            return RiskAssessment(
                level=RiskLevel.CRITICAL,
                reason_codes=(classification.intent.value,),
                requires_confirmation=False,
                contains_sensitive_data=True,
            )
        if classification.intent in HIGH_RISK_INTENTS:
            return RiskAssessment(
                level=RiskLevel.HIGH,
                reason_codes=("financial_action",),
                requires_confirmation=True,
            )
        if classification.intent in {Intent.ACCOUNT_INFORMATION, Intent.TRANSACTION_SEARCH}:
            return RiskAssessment(
                level=RiskLevel.MEDIUM,
                reason_codes=("sensitive_financial_data",),
                contains_sensitive_data=True,
            )
        return RiskAssessment(level=RiskLevel.LOW)

    def intent_allowed(self, intent: Intent) -> bool:
        return intent not in PROHIBITED_INTENTS and intent.value not in self.config.security.blocked_intents
