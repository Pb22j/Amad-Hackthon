"""Channel-level request and response shapes."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language


@dataclass(frozen=True)
class ChannelMessage:
    user_id: str
    content: str
    session_id: str | None = None
    language: Language | None = None


@dataclass(frozen=True)
class ChannelReply:
    session_id: str
    content: str
    language: Language

