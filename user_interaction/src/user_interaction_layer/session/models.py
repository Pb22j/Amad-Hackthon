"""Session state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from user_interaction_layer.agentic_client.schemas import Channel, Language, utc_now_iso


@dataclass
class SessionPreferences:
    voice: str = ""
    tone: str = "natural"
    arabic_variant: str = "msa"


@dataclass
class Session:
    user_id: str
    channel: Channel
    active_language: Language
    session_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    preferences: SessionPreferences = field(default_factory=SessionPreferences)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()


@dataclass
class InteractionTurn:
    session_id: str
    role: str
    channel: Channel
    language: Language
    content: str
    provider_metadata: dict[str, str] = field(default_factory=dict)
    turn_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now_iso)


@dataclass
class PendingTask:
    task_id: str
    request_id: str
    session_id: str
    status: str
    last_user_message: str
    last_user_safe_summary: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def update(self, status: str, user_safe_summary: str = "") -> None:
        self.status = status
        self.last_user_safe_summary = user_safe_summary or self.last_user_safe_summary
        self.updated_at = utc_now_iso()

