"""Render safe user-facing updates from agentic events."""

from __future__ import annotations

from user_interaction_layer.agentic_client.schemas import AgenticEvent, AgenticEventType, Language
from user_interaction_layer.security.redaction import redact_sensitive_text


ENGLISH_TEMPLATES = {
    AgenticEventType.ACCEPTED: "I'll check that now.",
    AgenticEventType.PROGRESS: "{summary}",
    AgenticEventType.INPUT_NEEDED: "{summary}",
    AgenticEventType.COMPLETED: "{summary}",
    AgenticEventType.FAILED: "I could not finish that yet. {summary}",
}

ARABIC_TEMPLATES = {
    AgenticEventType.ACCEPTED: "تمام، سأتحقق من ذلك الآن.",
    AgenticEventType.PROGRESS: "{summary}",
    AgenticEventType.INPUT_NEEDED: "{summary}",
    AgenticEventType.COMPLETED: "{summary}",
    AgenticEventType.FAILED: "لم أتمكن من إنهاء ذلك الآن. {summary}",
}


def render_agentic_event(event: AgenticEvent, language: Language) -> str:
    templates = ARABIC_TEMPLATES if language == Language.ARABIC else ENGLISH_TEMPLATES
    template = templates[event.event_type]

    if event.event_type == AgenticEventType.ACCEPTED:
        return template

    summary = _clean_summary(event.user_safe_summary)
    if not summary and event.event_type == AgenticEventType.FAILED:
        summary = _fallback_failure(language)
    elif not summary:
        summary = _fallback_update(language)

    return template.format(summary=summary).strip()


def _clean_summary(summary: str) -> str:
    redacted = redact_sensitive_text(summary.strip())
    blocked_fragments = ("traceback", "stack trace", "api_key", "system prompt")
    lowered = redacted.lower()
    if any(fragment in lowered for fragment in blocked_fragments):
        return ""
    return redacted


def _fallback_update(language: Language) -> str:
    if language == Language.ARABIC:
        return "وصلني تحديث على طلبك."
    return "I have an update on your request."


def _fallback_failure(language: Language) -> str:
    if language == Language.ARABIC:
        return "يمكننا المحاولة مرة أخرى أو مراجعة التفاصيل."
    return "We can try again or review the details."

