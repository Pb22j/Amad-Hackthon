"""Transactional outbox for reliable interaction-layer event delivery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.api.schemas import AgentEvent
from agentic.persistence.models import EventOutboxRow


class EventOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, event: AgentEvent) -> EventOutboxRow:
        row = EventOutboxRow(
            task_id=str(event.task_id),
            payload=event.model_dump(mode="json"),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def pending(self, *, limit: int = 20) -> list[EventOutboxRow]:
        now = datetime.now(timezone.utc)
        statement = (
            select(EventOutboxRow)
            .where(
                EventOutboxRow.delivered_at.is_(None),
                or_(
                    EventOutboxRow.next_attempt_at.is_(None),
                    EventOutboxRow.next_attempt_at <= now,
                ),
            )
            .order_by(EventOutboxRow.created_at, EventOutboxRow.id)
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def has_undelivered_predecessor(self, row: EventOutboxRow) -> bool:
        predecessor = await self.session.scalar(
            select(EventOutboxRow.id)
            .where(
                EventOutboxRow.task_id == row.task_id,
                EventOutboxRow.delivered_at.is_(None),
                or_(
                    EventOutboxRow.created_at < row.created_at,
                    and_(
                        EventOutboxRow.created_at == row.created_at,
                        EventOutboxRow.id < row.id,
                    ),
                ),
            )
            .limit(1)
        )
        return predecessor is not None

    async def delivered(self, row: EventOutboxRow) -> None:
        row.delivered_at = datetime.now(timezone.utc)
        row.last_error_code = None
        await self.session.flush()

    async def failed(self, row: EventOutboxRow, *, error_code: str) -> None:
        row.attempts += 1
        row.last_error_code = error_code[:100]
        delay_seconds = min(2 ** min(row.attempts, 8), 300)
        row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        await self.session.flush()
