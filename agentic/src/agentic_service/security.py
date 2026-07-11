"""Small security building blocks shared by API and workflow code."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any


class InvalidIban(ValueError):
    """Raised when an IBAN is not a valid Saudi IBAN."""


_IBAN_SPACE = re.compile(r"[\s-]+")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def normalize_saudi_iban(iban: str) -> str:
    """Normalize and validate a Saudi IBAN using the ISO 13616 MOD-97 check."""
    normalized = _IBAN_SPACE.sub("", iban).upper()
    if len(normalized) != 24 or not normalized.startswith("SA") or not normalized.isalnum():
        raise InvalidIban("a Saudi IBAN must start with SA and contain 24 alphanumeric characters")
    # Rearranging and converting letters to their ISO numeric representation
    # avoids platform integer limits while retaining the exact checksum rule.
    rearranged = normalized[4:] + normalized[:4]
    remainder = 0
    for character in rearranged:
        digits = str(ord(character) - 55) if "A" <= character <= "Z" else character
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    if remainder != 1:
        raise InvalidIban("Saudi IBAN checksum is invalid")
    return normalized


def mask_iban(iban: str) -> str:
    """Return an IBAN suitable for user-safe/audit output."""
    normalized = normalize_saudi_iban(iban)
    return f"{normalized[:4]}{'*' * (len(normalized) - 8)}{normalized[-4:]}"


def canonical_json(value: Any) -> str:
    """Canonical JSON used for idempotency payload hashes and signatures."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sign_payload(secret: str, body: bytes) -> str:
    """Create a SHA-256 HMAC, primarily for the callback adapter."""
    if not secret:
        raise ValueError("a non-empty webhook secret is required")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_payload_signature(secret: str, body: bytes, received_signature: str | None) -> bool:
    """Compare HMAC values in constant time; malformed input simply fails."""
    if not secret or not received_signature:
        return False
    candidate = received_signature.removeprefix("sha256=").lower()
    expected = sign_payload(secret, body)
    return hmac.compare_digest(expected, candidate)


def sanitize_user_text(value: str, *, max_length: int = 180) -> str:
    """Bound UI metadata without modifying payment authorization fields.

    Removes control characters and Unicode formatting controls, normalises
    whitespace and enforces a character limit.  It intentionally does not try
    to censor natural language; callers choose the context in which it is used.
    """
    if max_length < 1:
        raise ValueError("max_length must be positive")
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _CONTROL_CHARS.sub(" ", normalized)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")
    normalized = " ".join(normalized.split())
    return normalized[:max_length]


_SENSITIVE_KEYS = frozenset({
    "authorization", "access_token", "refresh_token", "id_token", "token", "otp",
    "password", "secret", "private_key", "client_secret", "iban",
})


def redact(value: Any) -> Any:
    """Recursively remove secrets from structured logs/audit details."""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _SENSITIVE_KEYS or normalized_key.endswith("_token"):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value
