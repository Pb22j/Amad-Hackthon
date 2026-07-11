"""Redaction helpers for financial logs and user-safe notifications."""

from __future__ import annotations

import re

CARD_OR_ACCOUNT_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SA_IBAN_RE = re.compile(r"\bSA\d{2}[A-Z0-9]{18}\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
SECRET_RE = re.compile(
    r"(?i)\b(api[_ -]?key|secret|token|password|passcode|otp|pin)\b\s*[:=]?\s*['\"]?[A-Za-z0-9._\-]{4,}"
)


def redact_sensitive_text(text: str) -> str:
    redacted = SA_IBAN_RE.sub("[REDACTED_IBAN]", text)
    redacted = CARD_OR_ACCOUNT_RE.sub("[REDACTED_NUMBER]", redacted)
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED_SECRET]", redacted)
    return redacted

