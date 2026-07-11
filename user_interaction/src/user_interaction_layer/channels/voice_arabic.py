"""Arabic voice channel adapter placeholder."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.channels.base import ChannelReply
from user_interaction_layer.orchestrator import UserInteractionOrchestrator
from user_interaction_layer.providers.arabic_voice import ArabicVoiceProvider


@dataclass
class ArabicVoiceChannel:
    provider: ArabicVoiceProvider
    orchestrator: UserInteractionOrchestrator

    def start(self, *, user_id: str) -> str:
        return self.provider.start_session(user_id=user_id, language=Language.ARABIC)

    def handle_final_transcript(
        self,
        *,
        user_id: str,
        transcript: str,
        session_id: str | None = None,
    ) -> ChannelReply:
        result = self.orchestrator.handle_voice_transcript(
            user_id=user_id,
            transcript=transcript,
            session_id=session_id,
            explicit_language=Language.ARABIC,
            source_provider="arabic_voice",
        )
        return ChannelReply(
            session_id=result.session_id,
            content=result.message_to_user,
            language=result.language,
        )
