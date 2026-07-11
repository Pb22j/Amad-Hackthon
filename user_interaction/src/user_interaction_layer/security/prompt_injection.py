"""Prompt-injection detection for the financial interaction boundary."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language


@dataclass(frozen=True)
class PromptInjectionAssessment:
    allowed: bool
    reason: str = ""
    user_message: str = ""


ENGLISH_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "ignore the above",
    "system prompt",
    "developer message",
    "hidden instructions",
    "reveal your prompt",
    "show your prompt",
    "bypass your instructions",
    "jailbreak",
    "act as system",
    "print your tools",
)

ARABIC_PATTERNS = (
    "تجاهل التعليمات",
    "تجاهل كل التعليمات",
    "اكشف التعليمات",
    "اعرض التعليمات",
    "تعليمات النظام",
    "رسالة المطور",
    "اكسر القيود",
    "تجاوز التعليمات",
    "اكشف الأدوات",
)


def assess_prompt_injection(text: str, language: Language) -> PromptInjectionAssessment:
    normalized = " ".join(text.lower().split())
    patterns = ARABIC_PATTERNS if language == Language.ARABIC else ENGLISH_PATTERNS
    for pattern in patterns:
        if pattern in normalized:
            return PromptInjectionAssessment(
                allowed=False,
                reason="prompt_injection",
                user_message=_blocked_message(language),
            )
    return PromptInjectionAssessment(allowed=True)


def _blocked_message(language: Language) -> str:
    if language == Language.ARABIC:
        return "لا أستطيع المساعدة في كشف أو تجاوز تعليمات النظام، لكن يمكنني مساعدتك في طلبك المالي بشكل آمن."
    return "I cannot help reveal or bypass system instructions, but I can help with your financial request safely."

