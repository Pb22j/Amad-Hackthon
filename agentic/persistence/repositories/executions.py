from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.persistence.models import ToolExecutionRow


class ToolExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_idempotency(
        self, *, tenant_id: str, idempotency_key: str
    ) -> ToolExecutionRow | None:
        statement = select(ToolExecutionRow).where(
            ToolExecutionRow.tenant_id == tenant_id,
            ToolExecutionRow.idempotency_key == idempotency_key,
        )
        return await self.session.scalar(statement)

    async def start(
        self,
        *,
        task_id: str,
        tenant_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str,
    ) -> tuple[ToolExecutionRow, bool]:
        existing = await self.get_by_idempotency(
            tenant_id=tenant_id, idempotency_key=idempotency_key
        )
        if existing:
            return existing, False
        row = ToolExecutionRow(
            task_id=task_id,
            tenant_id=tenant_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
            idempotency_key=idempotency_key,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            existing = await self.get_by_idempotency(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            )
            if existing is None:
                raise
            return existing, False
        return row, True

    async def complete(
        self,
        row: ToolExecutionRow,
        *,
        status: str,
        result: dict[str, Any] | None,
        receipt_id: str | None = None,
        operation_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        row.status = status
        row.result = result
        row.receipt_id = receipt_id
        row.operation_id = operation_id
        row.error_code = error_code
        row.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
