"""Replaceable Arabic speech-to-speech provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from user_interaction_layer.agentic_client.schemas import Language


@dataclass
class ArabicVoiceProvider:
    provider_name: str
    api_key: str

    def start_session(self, *, user_id: str, language: Language) -> str:
        if language != Language.ARABIC:
            raise ValueError("Arabic voice provider is configured only for Arabic voice sessions")
        if not self.provider_name or not self.api_key:
            raise ValueError("Arabic voice provider configuration is missing")
        return f"{self.provider_name}-{user_id}-{uuid4()}"

