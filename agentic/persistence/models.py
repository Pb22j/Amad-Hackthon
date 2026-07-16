"""Application-owned SQLAlchemy tables for durable tasks, memory, and audit."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agentic.security.crypto import EncryptedJSON, EncryptedText


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_string() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class AgentTaskRow(Base):
    __tablename__ = "agent_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_task_tenant_request"),
        Index("ix_tasks_identity", "tenant_id", "user_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    authorized_scopes: Mapped[list[str]] = mapped_column(EncryptedJSON, nullable=False, default=list)
    assurance_level: Mapped[str] = mapped_column(String(50), nullable=False)
    original_request: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    request_context: Mapped[dict[str, Any] | None] = mapped_column(
        EncryptedJSON, nullable=True, default=dict
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="received")
    intent: Mapped[str | None] = mapped_column(String(80))
    risk: Mapped[str | None] = mapped_column(String(40))
    agent_version: Mapped[str] = mapped_column(String(40), default="0.1.0")
    config_hash: Mapped[str | None] = mapped_column(String(64))
    request_fingerprint: Mapped[str | None] = mapped_column(String(64))
    final_report: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskEventRow(Base):
    __tablename__ = "task_events"
    __table_args__ = (Index("ix_task_events_task_created", "task_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EventOutboxRow(Base):
    __tablename__ = "event_outbox"
    __table_args__ = (
        Index("ix_event_outbox_pending", "delivered_at", "next_attempt_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ClarificationRow(Base):
    __tablename__ = "clarification_requests"
    __table_args__ = (Index("ix_clarification_task_status", "task_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    question: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_answer: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    answer: Mapped[Any | None] = mapped_column(EncryptedJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActionAuthorizationRow(Base):
    __tablename__ = "action_authorizations"
    __table_args__ = (
        UniqueConstraint("nonce", name="uq_authorization_nonce"),
        Index("ix_authorization_identity", "tenant_id", "user_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[str] = mapped_column(String(100), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    confirmation_method: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolExecutionRow(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_execution_idempotency"),
        Index("ix_execution_task_created", "task_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str] = mapped_column(ForeignKey("agent_tasks.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(200), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="started")
    error_code: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON)
    receipt_id: Mapped[str | None] = mapped_column(String(200))
    operation_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryItemRow(Base):
    __tablename__ = "memory_items"
    __table_args__ = (
        Index(
            "ix_memory_namespace",
            "tenant_id",
            "user_id",
            "session_id",
            "memory_type",
        ),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "session_id",
            "memory_type",
            "deduplication_key",
            name="uq_memory_item",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    memory_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_task_id: Mapped[str | None] = mapped_column(ForeignKey("agent_tasks.id"))
    provenance: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(30), nullable=False)
    consent_basis: Mapped[str] = mapped_column(String(100), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_identity_created", "tenant_id", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    task_id: Mapped[str | None] = mapped_column(String(36))
    tenant_id: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    decision: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(EncryptedJSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalRunRow(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(40), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    artifacts: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
