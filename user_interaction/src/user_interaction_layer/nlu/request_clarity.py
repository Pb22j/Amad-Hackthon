"""Request clarity checks owned by the interaction layer."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language


@dataclass(frozen=True)
class ClarityResult:
    clear: bool
    reason: str = ""
    question: str = ""


VAGUE_ENGLISH = {
    "do it",
    "fix it",
    "handle it",
    "that one",
    "this one",
    "check this",
    "please do",
}

VAGUE_ARABIC = {
    "سوها",
    "افعلها",
    "عدلها",
    "شيك عليها",
    "هذا",
    "هذه",
}


def check_request_clarity(text: str, language: Language) -> ClarityResult:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return ClarityResult(
            clear=False,
            reason="empty_request",
            question=_question(language),
        )

    lowered = cleaned.lower()
    vague_terms = VAGUE_ARABIC if language == Language.ARABIC else VAGUE_ENGLISH
    if len(cleaned) < 10 or lowered in vague_terms:
        return ClarityResult(
            clear=False,
            reason="too_vague",
            question=_question(language),
        )

    return ClarityResult(clear=True)


def _question(language: Language) -> str:
    if language == Language.ARABIC:
        return "ما الذي تريدني أن أراجعه بالتحديد؟"
    return "What would you like me to check specifically?"

