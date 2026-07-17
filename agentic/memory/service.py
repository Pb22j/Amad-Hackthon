"""Session-scoped persistence and deterministic compaction for curated memory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.memory.policy import MemoryPolicy
from agentic.persistence.models import MemoryItemRow
from agentic.security.identity import AuthContext


@dataclass(frozen=True, slots=True)
class MemoryCompactionReport:
    """Counts from a loss-averse compaction pass.

    Compaction never asks a model to rewrite memory. It only removes expired
    entries and lower-ranked, unverified overflow. Verified memories are never
    discarded merely to meet a size target.
    """

    expired: int = 0
    per_type_overflow: int = 0
    session_overflow: int = 0

    @property
    def deleted(self) -> int:
        return self.expired + self.per_type_overflow + self.session_overflow


class MemoryService:
    """Store policy-approved memory inside one authenticated session namespace."""

    def __init__(
        self,
        session: AsyncSession,
        policy: MemoryPolicy,
        *,
        max_items_per_session: int = 50,
        max_items_per_type: int = 5,
        max_value_characters: int = 4000,
    ) -> None:
        if max_items_per_type < 1 or max_items_per_session < max_items_per_type:
            raise ValueError("invalid memory compaction limits")
        self.session = session
        self.policy = policy
        self.max_items_per_session = max_items_per_session
        self.max_items_per_type = max_items_per_type
        self.max_value_characters = max_value_characters

    @staticmethod
    def _namespace(statement: Any, auth: AuthContext) -> Any:
        return statement.where(
            MemoryItemRow.tenant_id == auth.tenant_id,
            MemoryItemRow.user_id == auth.user_id,
            MemoryItemRow.session_id == auth.session_id,
        )

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
        """Validate, deduplicate, and stage one session-local memory item."""

        if not 0 <= confidence <= 1:
            raise ValueError("memory confidence must be between 0 and 1")
        self.policy.validate(memory_type, value)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(canonical) > self.max_value_characters:
            raise ValueError("memory value exceeds the configured size limit")
        deduplication_key = hashlib.sha256(canonical.encode()).hexdigest()
        statement = self._namespace(select(MemoryItemRow), auth).where(
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
            session_id=auth.session_id,
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
        await self.compact_session(auth=auth)
        return row

    async def list_for_session(
        self,
        *,
        auth: AuthContext,
        memory_types: set[str] | None = None,
        limit: int = 50,
    ) -> list[MemoryItemRow]:
        """Return unexpired memory from exactly one tenant/user/session tuple."""

        now = datetime.now(timezone.utc)
        statement = self._namespace(select(MemoryItemRow), auth).where(
            or_(MemoryItemRow.expires_at.is_(None), MemoryItemRow.expires_at > now)
        )
        if memory_types:
            statement = statement.where(MemoryItemRow.memory_type.in_(memory_types))
        statement = statement.order_by(
            MemoryItemRow.verified.desc(),
            MemoryItemRow.confidence.desc(),
            MemoryItemRow.created_at.desc(),
        ).limit(min(limit, self.max_items_per_session))
        return list(await self.session.scalars(statement))

    async def list_for_user(
        self,
        *,
        auth: AuthContext,
        memory_types: set[str] | None = None,
        limit: int = 50,
    ) -> list[MemoryItemRow]:
        """Compatibility alias; the authenticated session remains mandatory."""

        return await self.list_for_session(auth=auth, memory_types=memory_types, limit=limit)

    async def compact_session(self, *, auth: AuthContext) -> MemoryCompactionReport:
        """Compact one session without synthesizing or weakening trusted memory."""

        now = datetime.now(timezone.utc)
        all_rows = list(await self.session.scalars(self._namespace(select(MemoryItemRow), auth)))
        expired_rows = []
        active_rows = []
        for row in all_rows:
            expires_at = row.expires_at
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at is not None and expires_at <= now:
                expired_rows.append(row)
            else:
                active_rows.append(row)

        for row in expired_rows:
            await self.session.delete(row)

        def rank(row: MemoryItemRow) -> tuple[bool, float, datetime, str]:
            created = row.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            return row.verified, row.confidence, created, row.id

        per_type_removed: list[MemoryItemRow] = []
        retained: list[MemoryItemRow] = []
        memory_types = sorted({row.memory_type for row in active_rows})
        for memory_type in memory_types:
            rows = sorted(
                (row for row in active_rows if row.memory_type == memory_type),
                key=rank,
                reverse=True,
            )
            verified_rows = [row for row in rows if row.verified]
            unverified_rows = [row for row in rows if not row.verified]
            unverified_slots = max(self.max_items_per_type - len(verified_rows), 0)
            retained.extend(verified_rows)
            retained.extend(unverified_rows[:unverified_slots])
            per_type_removed.extend(unverified_rows[unverified_slots:])

        for row in per_type_removed:
            await self.session.delete(row)

        retained = sorted(retained, key=rank, reverse=True)
        verified_count = sum(row.verified for row in retained)
        effective_limit = max(self.max_items_per_session, verified_count)
        overflow = [row for row in retained[effective_limit:] if not row.verified]
        for row in overflow:
            await self.session.delete(row)

        await self.session.flush()
        return MemoryCompactionReport(
            expired=len(expired_rows),
            per_type_overflow=len(per_type_removed),
            session_overflow=len(overflow),
        )

    async def delete_for_session(self, *, auth: AuthContext) -> int:
        """Delete curated memory belonging only to the authenticated session."""

        result = await self.session.execute(self._namespace(delete(MemoryItemRow), auth))
        return result.rowcount or 0

    async def delete_for_user(self, *, auth: AuthContext) -> int:
        """Compatibility alias for session-scoped deletion."""

        return await self.delete_for_session(auth=auth)
