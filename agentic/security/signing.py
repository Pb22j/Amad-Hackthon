from __future__ import annotations

import hashlib
import hmac
import time


class InteractionSignatureVerifier:
    def __init__(self, secret: str | bytes, *, max_age_seconds: int = 300) -> None:
        self.secret = secret.encode() if isinstance(secret, str) else secret
        if len(self.secret) < 32:
            raise ValueError("interaction signing secret must contain at least 32 bytes")
        self.max_age_seconds = max_age_seconds

    def sign(self, body: bytes, timestamp: int | None = None) -> tuple[str, str]:
        value = str(timestamp or int(time.time()))
        signature = hmac.new(self.secret, value.encode() + b"." + body, hashlib.sha256).hexdigest()
        return value, signature

    def verify(self, body: bytes, timestamp: str, signature: str) -> None:
        try:
            numeric_timestamp = int(timestamp)
        except ValueError as exc:
            raise PermissionError("invalid request timestamp") from exc
        if abs(int(time.time()) - numeric_timestamp) > self.max_age_seconds:
            raise PermissionError("request signature has expired")
        expected = hmac.new(
            self.secret, timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise PermissionError("invalid request signature")

