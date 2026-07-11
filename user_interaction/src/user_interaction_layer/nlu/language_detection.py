"""Small language detector for English and Arabic interaction routing."""

from __future__ import annotations

import re

from user_interaction_layer.agentic_client.schemas import Language

ARABIC_RE = re.compile(r"[\u0600-\u06ff]")


def detect_language(text: str, explicit_language: str | Language | None = None) -> Language:
    if explicit_language:
        return Language(explicit_language)

    if ARABIC_RE.search(text):
        return Language.ARABIC

    return Language.ENGLISH

