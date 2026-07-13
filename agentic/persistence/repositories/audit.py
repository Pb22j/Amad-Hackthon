"""Repository for append-only agent security decisions."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agentic.persistence.models import AuditEventRow
from agentic.security.redaction import redact


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        task_id: str | None,
        tenant_id: str,
        user_id: str,
        category: str,
        decision: str,
        reason_code: str,
        details: dict[str, Any] | None = None,
    ) -> AuditEventRow:
        row = AuditEventRow(
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            category=category,
            decision=decision,
            reason_code=reason_code,
            details=redact(details or {}),
        )
        self.session.add(row)
        await self.session.flush()
        return row
