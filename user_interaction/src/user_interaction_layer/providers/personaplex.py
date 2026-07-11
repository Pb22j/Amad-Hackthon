"""PersonaPlex voice provider adapter placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from user_interaction_layer.agentic_client.schemas import Language


@dataclass
class PersonaPlexVoiceProvider:
    api_key: str
    agent_id: str

    def start_session(self, *, user_id: str, language: Language) -> str:
        if language != Language.ENGLISH:
            raise ValueError("PersonaPlex is configured only for English voice sessions")
        if not self.api_key or not self.agent_id:
            raise ValueError("PersonaPlex credentials are missing")
        return f"personaplex-{user_id}-{uuid4()}"

