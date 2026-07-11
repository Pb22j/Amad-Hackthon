"""Turn-based voice pipeline that preserves the single agentic API boundary."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.orchestrator import UserInteractionOrchestrator
from user_interaction_layer.voice.models import AudioInput, VoiceTurnResult
from user_interaction_layer.voice.providers import VoiceAudioProvider


@dataclass
class VoiceInteractionService:
    orchestrator: UserInteractionOrchestrator
    audio_provider: VoiceAudioProvider

    async def handle_audio_turn(
        self,
        *,
        user_id: str,
        audio: AudioInput,
        language: Language,
        source_provider: str,
        session_id: str | None = None,
    ) -> VoiceTurnResult:
        transcript = await self.audio_provider.transcribe(audio, language)
        interaction = self.orchestrator.handle_voice_transcript(
            user_id=user_id,
            transcript=transcript.text,
            source_provider=source_provider,
            session_id=session_id,
            explicit_language=language,
        )
        speech = await self.audio_provider.synthesize(interaction.message_to_user, interaction.language)
        return VoiceTurnResult(
            session_id=interaction.session_id,
            transcript=transcript.text,
            message_to_user=interaction.message_to_user,
            decision_type=interaction.decision_type.value,
            language=interaction.language,
            task_id=interaction.task_id,
            request_id=interaction.request_id,
            audio=speech.audio,
            audio_mime_type=speech.mime_type,
            audio_format=speech.format,
            provider=speech.provider,
        )

    async def handle_text_turn(
        self,
        *,
        user_id: str,
        transcript: str,
        language: Language,
        source_provider: str,
        session_id: str | None = None,
    ) -> VoiceTurnResult:
        interaction = self.orchestrator.handle_voice_transcript(
            user_id=user_id,
            transcript=transcript,
            source_provider=source_provider,
            session_id=session_id,
            explicit_language=language,
        )
        speech = await self.audio_provider.synthesize(interaction.message_to_user, interaction.language)
        return VoiceTurnResult(
            session_id=interaction.session_id,
            transcript=transcript,
            message_to_user=interaction.message_to_user,
            decision_type=interaction.decision_type.value,
            language=interaction.language,
            task_id=interaction.task_id,
            request_id=interaction.request_id,
            audio=speech.audio,
            audio_mime_type=speech.mime_type,
            audio_format=speech.format,
            provider=speech.provider,
        )
