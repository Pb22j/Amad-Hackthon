from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.persistence.models import ActionAuthorizationRow
from agentic.security.confirmation import ConfirmationClaims


class AuthorizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def consume(self, claims: ConfirmationClaims) -> ActionAuthorizationRow:
        statement = select(ActionAuthorizationRow).where(ActionAuthorizationRow.nonce == claims.nonce)
        row = await self.session.scalar(statement)
        if row is None:
            row = ActionAuthorizationRow(
                task_id=claims.task_id,
                user_id=claims.user_id,
                tenant_id=claims.tenant_id,
                tool_name=claims.tool_name,
                arguments_hash=claims.arguments_hash,
                nonce=claims.nonce,
                issuer=claims.issuer,
                confirmation_method=claims.confirmation_method,
                created_at=claims.issued_at,
                expires_at=claims.expires_at,
            )
            self.session.add(row)
            await self.session.flush()
        if row.consumed_at is not None:
            raise PermissionError("authorization has already been used")
        if claims.expires_at <= datetime.now(timezone.utc):
            raise PermissionError("authorization has expired")
        row.consumed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return row

