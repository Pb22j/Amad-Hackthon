from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentic.security.identity import AuthContext


class ConfirmationClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    user_id: str
    tenant_id: str
    tool_name: str
    arguments_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str
    issuer: str
    confirmation_method: str
    issued_at: datetime
    expires_at: datetime


def normalize_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(normalize_arguments(arguments).encode("utf-8")).hexdigest()


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class ConfirmationSigner:
    """Signs exact financial actions; nonce consumption is enforced by the repository."""

    def __init__(self, key: str | bytes, *, issuer: str = "interaction-layer") -> None:
        self.key = key.encode() if isinstance(key, str) else key
        if len(self.key) < 32:
            raise ValueError("confirmation signing key must contain at least 32 bytes")
        self.issuer = issuer

    def issue(
        self,
        *,
        auth: AuthContext,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        confirmation_method: str = "explicit",
        ttl_seconds: int = 300,
    ) -> str:
        now = datetime.now(timezone.utc)
        claims = ConfirmationClaims(
            task_id=task_id,
            user_id=auth.user_id,
            tenant_id=auth.tenant_id,
            tool_name=tool_name,
            arguments_hash=arguments_hash(arguments),
            nonce=secrets.token_urlsafe(24),
            issuer=self.issuer,
            confirmation_method=confirmation_method,
            issued_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        payload = claims.model_dump_json().encode("utf-8")
        encoded = _encode(payload)
        signature = _encode(hmac.new(self.key, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        *,
        auth: AuthContext,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        now: datetime | None = None,
    ) -> ConfirmationClaims:
        try:
            encoded, supplied_signature = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("malformed authorization token") from exc
        expected_signature = _encode(
            hmac.new(self.key, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("invalid authorization signature")
        try:
            claims = ConfirmationClaims.model_validate_json(_decode(encoded))
        except Exception as exc:
            raise ValueError("invalid authorization claims") from exc
        current = now or datetime.now(timezone.utc)
        if claims.expires_at <= current:
            raise ValueError("authorization has expired")
        if claims.issued_at > current + timedelta(seconds=30):
            raise ValueError("authorization issue time is invalid")
        expected = (
            auth.user_id,
            auth.tenant_id,
            task_id,
            tool_name,
            arguments_hash(arguments),
            self.issuer,
        )
        actual = (
            claims.user_id,
            claims.tenant_id,
            claims.task_id,
            claims.tool_name,
            claims.arguments_hash,
            claims.issuer,
        )
        if not all(hmac.compare_digest(a, b) for a, b in zip(expected, actual, strict=True)):
            raise PermissionError("authorization does not match this exact action")
        return claims

