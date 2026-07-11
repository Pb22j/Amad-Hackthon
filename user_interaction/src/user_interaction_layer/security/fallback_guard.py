"""Deterministic fallback for when the LLM guard is unavailable."""

from __future__ import annotations

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.security.llm_guard import (
    GuardAction,
    GuardRiskLevel,
    SecurityGuardAssessment,
)
from user_interaction_layer.security.privacy import assess_financial_privacy
from user_interaction_layer.security.prompt_injection import assess_prompt_injection


def assess_with_deterministic_fallback(text: str, language: Language) -> SecurityGuardAssessment:
    prompt_assessment = assess_prompt_injection(text, language)
    if not prompt_assessment.allowed:
        return SecurityGuardAssessment(
            action=GuardAction.REFUSE,
            risk_level=GuardRiskLevel.HIGH,
            reason=prompt_assessment.reason,
            categories=["prompt_injection"],
            user_message_en=prompt_assessment.user_message if language == Language.ENGLISH else "",
            user_message_ar=prompt_assessment.user_message if language == Language.ARABIC else "",
        )

    privacy_assessment = assess_financial_privacy(text, language)
    if not privacy_assessment.allowed:
        return SecurityGuardAssessment(
            action=GuardAction.REFUSE,
            risk_level=GuardRiskLevel.HIGH,
            reason=privacy_assessment.reason,
            categories=[privacy_assessment.reason],
            user_message_en=privacy_assessment.user_message if language == Language.ENGLISH else "",
            user_message_ar=privacy_assessment.user_message if language == Language.ARABIC else "",
        )

    return SecurityGuardAssessment(
        action=GuardAction.ALLOW,
        risk_level=GuardRiskLevel.LOW,
        reason="deterministic_fallback_allow",
        categories=["safe_financial_request"],
    )

