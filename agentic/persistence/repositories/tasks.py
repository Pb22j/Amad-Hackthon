from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.api.schemas import AgenticRequest, TERMINAL_TASK_STATUSES, TaskStatus
from agentic.persistence.models import AgentTaskRow, TaskEventRow


ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.RECEIVED: frozenset({TaskStatus.VALIDATING, TaskStatus.REJECTED, TaskStatus.FAILED}),
    TaskStatus.VALIDATING: frozenset({TaskStatus.RUNNING, TaskStatus.REJECTED, TaskStatus.FAILED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING_FOR_INPUT,
            TaskStatus.WAITING_FOR_CONFIRMATION,
            TaskStatus.COMPLETED,
            TaskStatus.PARTIALLY_COMPLETED,
            TaskStatus.REJECTED,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.WAITING_FOR_INPUT: frozenset(
        {TaskStatus.RUNNING, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.EXPIRED}
    ),
    TaskStatus.WAITING_FOR_CONFIRMATION: frozenset(
        {TaskStatus.RUNNING, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.EXPIRED}
    ),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.PARTIALLY_COMPLETED: frozenset(),
    TaskStatus.REJECTED: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.EXPIRED: frozenset(),
}


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, request: AgenticRequest, *, config_hash: str) -> AgentTaskRow:
        existing = await self.get_by_request(str(request.request_id), request.tenant_id)
        if existing:
            return existing
        row = AgentTaskRow(
            request_id=str(request.request_id),
            session_id=str(request.session_id),
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            language=request.language,
            authorized_scopes=sorted(request.authorization.scopes),
            assurance_level=request.authorization.assurance_level,
            original_request=request.natural_language_request,
            status=TaskStatus.RECEIVED.value,
            config_hash=config_hash,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            existing = await self.get_by_request(str(request.request_id), request.tenant_id)
            if existing is None:
                raise
            return existing
        await self.add_event(row.id, "accepted", {})
        return row

    async def get(self, task_id: str, *, tenant_id: str, user_id: str) -> AgentTaskRow | None:
        statement = select(AgentTaskRow).where(
            AgentTaskRow.id == task_id,
            AgentTaskRow.tenant_id == tenant_id,
            AgentTaskRow.user_id == user_id,
        )
        return await self.session.scalar(statement)

    async def get_by_request(self, request_id: str, tenant_id: str) -> AgentTaskRow | None:
        statement = select(AgentTaskRow).where(
            AgentTaskRow.request_id == request_id,
            AgentTaskRow.tenant_id == tenant_id,
        )
        return await self.session.scalar(statement)

    async def transition(
        self,
        row: AgentTaskRow,
        target: TaskStatus,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        current = TaskStatus(row.status)
        if target not in ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"invalid task transition: {current.value} -> {target.value}")
        row.status = target.value
        row.updated_at = datetime.now(timezone.utc)
        if target in TERMINAL_TASK_STATUSES:
            row.completed_at = row.updated_at
        await self.add_event(row.id, target.value, payload or {})
        await self.session.flush()

    async def add_event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.session.add(TaskEventRow(task_id=task_id, event_type=event_type, payload=payload))
        await self.session.flush()
