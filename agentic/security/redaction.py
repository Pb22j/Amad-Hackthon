from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


SECRET_KEY_PATTERN = re.compile(
    r"(?:password|passcode|pin|otp|token|secret|api[_-]?key|cvv|authorization)", re.IGNORECASE
)
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
BEARER_PATTERN = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
API_KEY_PATTERN = re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{16,}\b")


def redact_text(value: str) -> str:
    value = BEARER_PATTERN.sub("[REDACTED_AUTHORIZATION]", value)
    value = API_KEY_PATTERN.sub("[REDACTED_API_KEY]", value)
    value = CARD_PATTERN.sub("[REDACTED_CARD_NUMBER]", value)
    return value


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if SECRET_KEY_PATTERN.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact(item) for item in value]
    return value

