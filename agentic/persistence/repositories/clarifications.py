"""Persistence for clarification questions, answers, and expiration."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from jsonschema import ValidationError, validate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic.persistence.models import ClarificationRow


_TRUE_WORDS = {"true", "yes", "1", "نعم", "ايوه", "اي", "أجل"}
_FALSE_WORDS = {"false", "no", "0", "لا", "كلا"}


def _fold_digits(text: str) -> str:
    """Fold Arabic-Indic (and other Unicode) digits to ASCII."""

    return "".join(
        str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text
    )


def coerce_clarification_answer(answer: Any, schema: dict[str, Any]) -> Any:
    """Coerce a string answer to the schema's scalar type before validation.

    Interaction clients send free-text answers, so a number-typed clarification
    receives "50" (a string) and jsonschema rejected it, which surfaced to the
    user as the same question being asked again forever. Convert obvious numeric
    and boolean strings (including Arabic-Indic digits) so a well-formed answer
    is accepted; anything ambiguous is left untouched for the validator to judge.
    """

    if not isinstance(answer, str):
        return answer
    expected = schema.get("type") if isinstance(schema, dict) else None
    text = _fold_digits(answer.strip())
    if expected in {"number", "integer"}:
        try:
            number = float(text)
        except ValueError:
            return answer
        if expected == "integer":
            return int(number) if number.is_integer() else answer
        return int(number) if number.is_integer() else number
    if expected == "boolean":
        lowered = text.casefold()
        if lowered in _TRUE_WORDS:
            return True
        if lowered in _FALSE_WORDS:
            return False
    return answer


class ClarificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        clarification_id: str | None = None,
        task_id: str,
        question: str,
        reason_code: str,
        expected_answer: dict[str, Any],
        expires_in_seconds: int,
    ) -> ClarificationRow:
        if clarification_id:
            existing = await self.session.get(ClarificationRow, clarification_id)
            if existing:
                return existing
        row = ClarificationRow(
            id=clarification_id,
            task_id=task_id,
            question=question,
            reason_code=reason_code,
            expected_answer=expected_answer,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def answer(self, clarification_id: str, *, task_id: str, answer: Any) -> ClarificationRow:
        statement = select(ClarificationRow).where(
            ClarificationRow.id == clarification_id,
            ClarificationRow.task_id == task_id,
            ClarificationRow.status == "pending",
        )
        row = await self.session.scalar(statement)
        if row is None:
            raise ValueError("clarification is missing, expired, or already answered")
        now = datetime.now(timezone.utc)
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            row.status = "expired"
            raise ValueError("clarification has expired")
        answer = coerce_clarification_answer(answer, row.expected_answer)
        try:
            validate(instance=answer, schema=row.expected_answer)
        except ValidationError as exc:
            raise ValueError("clarification answer does not match the expected schema") from exc
        row.answer = answer
        row.status = "answered"
        row.answered_at = now
        await self.session.flush()
        return row

    async def answered_values(self, task_id: str) -> tuple[Any, ...]:
        """Return values supplied through authenticated clarification resumes."""

        statement = (
            select(ClarificationRow.answer)
            .where(
                ClarificationRow.task_id == task_id,
                ClarificationRow.status == "answered",
            )
            .order_by(ClarificationRow.answered_at)
        )
        return tuple(await self.session.scalars(statement))

    async def answered_field_values(self, task_id: str) -> dict[str, tuple[Any, ...]]:
        """Return authenticated clarification answers bound to their requested field."""

        statement = (
            select(
                ClarificationRow.expected_answer,
                ClarificationRow.reason_code,
                ClarificationRow.answer,
            )
            .where(
                ClarificationRow.task_id == task_id,
                ClarificationRow.status == "answered",
            )
            .order_by(ClarificationRow.answered_at)
        )
        values: dict[str, list[Any]] = {}
        for expected_answer, reason_code, answer in await self.session.execute(statement):
            field_name = expected_answer.get("field") if isinstance(expected_answer, dict) else None
            # Models sometimes use the generic clarification field name
            # ``answer`` even though the reason code identifies the protected
            # tool argument. Preserve the authenticated answer as evidence for
            # that exact argument so a resumed guarded tool does not ask the
            # same question again and reuse an already-answered interrupt.
            if field_name in {None, "", "answer"}:
                for prefix in ("missing_explicit_", "missing_"):
                    if reason_code.startswith(prefix) and len(reason_code) > len(prefix):
                        field_name = reason_code[len(prefix) :]
                        break
            if isinstance(field_name, str) and field_name:
                values.setdefault(field_name, []).append(answer)
        return {name: tuple(answers) for name, answers in values.items()}
