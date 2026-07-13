"""Retention queries for expired memories and nonterminal task checkpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.api.schemas import TERMINAL_TASK_STATUSES, TaskStatus
from agentic.persistence.models import AgentTaskRow, MemoryItemRow


class RetentionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def cleanup_expired(self, *, now: datetime | None = None) -> tuple[list[str], int]:
        current = now or datetime.now(timezone.utc)
        result = await self.session.scalars(
            select(AgentTaskRow).where(
                AgentTaskRow.expires_at.is_not(None),
                AgentTaskRow.expires_at <= current,
            )
        )
        tasks = list(result)
        for task in tasks:
            if TaskStatus(task.status) not in TERMINAL_TASK_STATUSES:
                task.status = TaskStatus.EXPIRED.value
                task.completed_at = current
            task.expires_at = None
            task.updated_at = current
        deleted = await self.session.execute(
            delete(MemoryItemRow).where(
                MemoryItemRow.expires_at.is_not(None),
                MemoryItemRow.expires_at <= current,
            )
        )
        await self.session.flush()
        return [task.id for task in tasks], deleted.rowcount or 0
