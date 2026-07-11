"""Provider interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from user_interaction_layer.agentic_client.schemas import Language


@dataclass(frozen=True)
class ChatProviderResponse:
    text: str
    model: str
    metadata: dict[str, str]


class ChatProvider(Protocol):
    def complete(self, *, messages: list[dict[str, str]], language: Language) -> ChatProviderResponse:
        """Generate or classify chat text."""


class VoiceProvider(Protocol):
    def start_session(self, *, user_id: str, language: Language) -> str:
        """Start a voice session and return the provider session id."""

