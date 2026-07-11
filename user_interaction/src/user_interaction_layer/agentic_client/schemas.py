"""Schemas for the single natural-language agentic API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Channel(str, Enum):
    CHAT = "chat"
    VOICE = "voice"


class Language(str, Enum):
    ENGLISH = "en"
    ARABIC = "ar"


class AgenticStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AgenticEventType(str, Enum):
    ACCEPTED = "accepted"
    PROGRESS = "progress"
    INPUT_NEEDED = "input_needed"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class Confirmation:
    required: bool = False
    received: bool = False

    def to_payload(self) -> dict[str, bool]:
        return {
            "required": self.required,
            "received": self.received,
        }


@dataclass(frozen=True)
class AgenticRequest:
    request_id: str
    session_id: str
    user_id: str
    channel: Channel
    language: Language
    natural_language_request: str
    original_user_message: str
    source_provider: str
    confirmation: Confirmation = field(default_factory=Confirmation)
    conversation_context_summary: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel": self.channel.value,
            "language": self.language.value,
            "natural_language_request": self.natural_language_request,
            "original_user_message": self.original_user_message,
            "confirmation": self.confirmation.to_payload(),
            "metadata": {
                "created_at": self.created_at,
                "source_provider": self.source_provider,
                "conversation_context_summary": self.conversation_context_summary,
            },
        }


@dataclass(frozen=True)
class AgenticResponse:
    request_id: str
    task_id: str
    status: AgenticStatus
    user_safe_message: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AgenticResponse":
        return cls(
            request_id=str(payload["request_id"]),
            task_id=str(payload["task_id"]),
            status=AgenticStatus(payload["status"]),
            user_safe_message=str(payload.get("user_safe_message", "")),
        )


@dataclass(frozen=True)
class AgenticEvent:
    task_id: str
    request_id: str
    session_id: str
    event_type: AgenticEventType
    user_safe_summary: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AgenticEvent":
        return cls(
            task_id=str(payload["task_id"]),
            request_id=str(payload["request_id"]),
            session_id=str(payload["session_id"]),
            event_type=AgenticEventType(payload["event_type"]),
            user_safe_summary=str(payload.get("user_safe_summary", "")),
            details=dict(payload.get("details", {})),
            created_at=str(payload.get("created_at", utc_now_iso())),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "user_safe_summary": self.user_safe_summary,
            "details": self.details,
            "created_at": self.created_at,
        }
