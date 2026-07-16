"""Trusted runtime identity and deterministic scope enforcement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthContext:
    user_id: str
    tenant_id: str
    session_id: str
    scopes: frozenset[str]

    def require_scopes(self, required: frozenset[str]) -> None:
        missing = required - self.scopes
        if missing:
            raise PermissionError(f"missing required scopes: {sorted(missing)}")

    def matches(self, *, user_id: str, tenant_id: str, session_id: str | None = None) -> bool:
        return (
            self.user_id == user_id
            and self.tenant_id == tenant_id
            and (session_id is None or self.session_id == session_id)
        )
