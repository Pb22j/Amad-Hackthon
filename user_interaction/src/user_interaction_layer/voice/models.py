"""Voice request and response models."""

from __future__ import annotations

from dataclasses import dataclass

from user_interaction_layer.agentic_client.schemas import Language


@dataclass(frozen=True)
class AudioInput:
    data: bytes
    mime_type: str = "audio/wav"
    filename: str = "input.wav"


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    language: Language


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    provider: str
    mime_type: str
    format: str


@dataclass(frozen=True)
class VoiceTurnResult:
    session_id: str
    transcript: str
    message_to_user: str
    decision_type: str
    language: Language
    task_id: str
    request_id: str
    audio: bytes
    audio_mime_type: str
    audio_format: str
    provider: str

