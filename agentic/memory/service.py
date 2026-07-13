"""Tenant- and user-scoped persistence for curated long-term memory."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.memory.policy import MemoryPolicy
from agentic.persistence.models import MemoryItemRow
from agentic.security.identity import AuthContext


class MemoryService:
    """Store only policy-approved memories with provenance and expiration."""

    def __init__(self, session: AsyncSession, policy: MemoryPolicy) -> None:
        self.session = session
        self.policy = policy

    async def put(
        self,
        *,
        auth: AuthContext,
        memory_type: str,
        value: dict[str, Any],
        provenance: str,
        confidence: float,
        sensitivity: str,
        consent_basis: str,
        source_task_id: str | None = None,
        expires_at: datetime | None = None,
        verified: bool = False,
    ) -> MemoryItemRow:
        """Validate, deduplicate, and stage one curated memory item."""

        if not 0 <= confidence <= 1:
            raise ValueError("memory confidence must be between 0 and 1")
        self.policy.validate(memory_type, value)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        deduplication_key = hashlib.sha256(canonical.encode()).hexdigest()
        statement = select(MemoryItemRow).where(
            MemoryItemRow.tenant_id == auth.tenant_id,
            MemoryItemRow.user_id == auth.user_id,
            MemoryItemRow.memory_type == memory_type,
            MemoryItemRow.deduplication_key == deduplication_key,
        )
        existing = await self.session.scalar(statement)
        if existing:
            return existing
        now = datetime.now(timezone.utc)
        row = MemoryItemRow(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            memory_type=memory_type,
            value=value,
            deduplication_key=deduplication_key,
            source_task_id=source_task_id,
            provenance=provenance,
            confidence=confidence,
            sensitivity=sensitivity,
            consent_basis=consent_basis,
            verified=verified,
            verified_at=now if verified else None,
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_user(
        self,
        *,
        auth: AuthContext,
        memory_types: set[str] | None = None,
        limit: int = 50,
    ) -> list[MemoryItemRow]:
        """Return unexpired memories from exactly one tenant/user namespace."""

        now = datetime.now(timezone.utc)
        statement = select(MemoryItemRow).where(
            MemoryItemRow.tenant_id == auth.tenant_id,
            MemoryItemRow.user_id == auth.user_id,
            or_(MemoryItemRow.expires_at.is_(None), MemoryItemRow.expires_at > now),
        )
        if memory_types:
            statement = statement.where(MemoryItemRow.memory_type.in_(memory_types))
        statement = statement.order_by(MemoryItemRow.created_at.desc()).limit(min(limit, 100))
        result = await self.session.scalars(statement)
        return list(result)

    async def delete_for_user(self, *, auth: AuthContext) -> int:
        """Delete every curated item belonging to the authenticated namespace."""

        statement = delete(MemoryItemRow).where(
            MemoryItemRow.tenant_id == auth.tenant_id,
            MemoryItemRow.user_id == auth.user_id,
        )
        result = await self.session.execute(statement)
        return result.rowcount or 0
