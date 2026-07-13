"""Strict external API schemas and the durable task-status state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    REJECTED = "rejected"
    FAILED = "failed"
    EXPIRED = "expired"


TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.PARTIALLY_COMPLETED,
    TaskStatus.REJECTED,
    TaskStatus.FAILED,
    TaskStatus.EXPIRED,
}


class AgentEventType(StrEnum):
    ACCEPTED = "accepted"
    PROGRESS = "progress"
    INPUT_NEEDED = "input_needed"
    CONFIRMATION_NEEDED = "confirmation_needed"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class ConfirmationMetadata(StrictSchema):
    authorization_token: str | None = Field(default=None, repr=False)


class AuthorizationContext(StrictSchema):
    scopes: frozenset[str] = Field(min_length=1)
    authenticated_at: datetime
    assurance_level: str = Field(min_length=1, max_length=50)


class RequestMetadata(StrictSchema):
    created_at: datetime = Field(default_factory=utc_now)
    conversation_context_summary: str | None = Field(default=None, max_length=10_000)
    source_provider: str | None = Field(default=None, max_length=100)


class AgenticRequest(StrictSchema):
    request_id: UUID
    session_id: UUID
    user_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)
    language: Literal["en", "ar"]
    natural_language_request: str = Field(min_length=1, max_length=20_000)
    original_user_message: str = Field(min_length=1, max_length=20_000)
    authorization: AuthorizationContext
    confirmation: ConfirmationMetadata | None = None
    metadata: RequestMetadata = Field(default_factory=RequestMetadata)


class AcceptedTask(StrictSchema):
    request_id: UUID
    task_id: UUID
    status: Literal["accepted", "rejected"]
    user_safe_message: str | None = Field(default=None, max_length=500)


class ResumeTaskRequest(StrictSchema):
    request_id: UUID
    session_id: UUID
    user_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)
    clarification_id: UUID | None = None
    answer: Any | None = None
    authorization_token: str | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def exactly_one_resume_value(self) -> "ResumeTaskRequest":
        has_answer = self.clarification_id is not None and self.answer is not None
        has_confirmation = self.authorization_token is not None
        if (self.clarification_id is None) != (self.answer is None):
            raise ValueError("clarification_id and answer must be provided together")
        if has_answer == has_confirmation:
            raise ValueError("provide either a clarification answer or an authorization token")
        return self


class TaskStatusRequest(StrictSchema):
    """Authenticated identity tuple used by the temporary evaluation poller."""

    request_id: UUID
    session_id: UUID
    user_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)


class TaskStatusResponse(StrictSchema):
    """Safe task state returned by the non-production evaluation endpoint."""

    task_id: UUID
    status: TaskStatus
    final_report: dict[str, Any] | None = None
    pending_action: dict[str, Any] | None = None


class MemoryDeleteRequest(StrictSchema):
    request_id: UUID
    session_id: UUID
    user_id: str = Field(min_length=1, max_length=200)
    tenant_id: str = Field(min_length=1, max_length=200)


class AgentEvent(StrictSchema):
    task_id: UUID
    request_id: UUID
    session_id: UUID
    event_type: AgentEventType
    user_safe_summary: str = Field(max_length=1000)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class HealthResponse(StrictSchema):
    status: Literal["ok", "degraded"]
    version: str
