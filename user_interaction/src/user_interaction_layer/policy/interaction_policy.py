"""Conversation policy for privacy-safe agentic dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.nlu.request_clarity import check_request_clarity
from user_interaction_layer.security.fallback_guard import assess_with_deterministic_fallback
from user_interaction_layer.security.llm_guard import (
    GuardAction,
    SecurityGuard,
    SecurityGuardError,
)


class DecisionType(str, Enum):
    DISPATCH = "dispatch"
    CLARIFY = "clarify"
    REFUSE = "refuse"


@dataclass(frozen=True)
class PolicyDecision:
    decision_type: DecisionType
    user_message: str = ""
    reason: str = ""


@dataclass
class InteractionPolicy:
    """Keeps UX guardrails separate from financial business approvals."""

    security_guard: SecurityGuard | None = None
    require_security_guard: bool = False

    def evaluate(
        self,
        text: str,
        language: Language,
        conversation_context_summary: str = "",
    ) -> PolicyDecision:
        if self.require_security_guard and not self.security_guard:
            return PolicyDecision(
                decision_type=DecisionType.REFUSE,
                user_message=_guard_unavailable_message(language),
                reason="security_guard_unavailable",
            )

        try:
            security_assessment = (
                self.security_guard.assess(
                    text=text,
                    language=language,
                    conversation_context_summary=conversation_context_summary,
                )
                if self.security_guard
                else assess_with_deterministic_fallback(text, language)
            )
        except SecurityGuardError:
            if self.require_security_guard:
                return PolicyDecision(
                    decision_type=DecisionType.REFUSE,
                    user_message=_guard_unavailable_message(language),
                    reason="security_guard_unavailable",
                )
            security_assessment = assess_with_deterministic_fallback(text, language)

        if security_assessment.action == GuardAction.REFUSE:
            return PolicyDecision(
                decision_type=DecisionType.REFUSE,
                user_message=security_assessment.user_message(language),
                reason=security_assessment.reason or _first_category(security_assessment.categories),
            )

        if security_assessment.action == GuardAction.CLARIFY:
            return PolicyDecision(
                decision_type=DecisionType.CLARIFY,
                user_message=security_assessment.user_message(language),
                reason=security_assessment.reason or _first_category(security_assessment.categories),
            )

        clarity = check_request_clarity(text, language)
        if not clarity.clear:
            return PolicyDecision(
                decision_type=DecisionType.CLARIFY,
                user_message=clarity.question,
                reason=clarity.reason,
            )

        return PolicyDecision(decision_type=DecisionType.DISPATCH)


def _guard_unavailable_message(language: Language) -> str:
    if language == Language.ARABIC:
        return "لا أستطيع متابعة الطلب الآن لأن فحص الأمان غير متاح. يمكننا المحاولة بعد قليل."
    return "I cannot continue that request right now because the security check is unavailable. We can try again shortly."


def _first_category(categories: list[str]) -> str:
    return categories[0] if categories else "security_guard_blocked"
