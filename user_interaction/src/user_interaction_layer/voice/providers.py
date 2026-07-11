"""Voice audio providers for transcription and speech synthesis."""

from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Protocol

import httpx

from user_interaction_layer.agentic_client.schemas import Language
from user_interaction_layer.voice.models import AudioInput, SpeechResult, TranscriptionResult


class VoiceProviderError(RuntimeError):
    """Raised when a voice provider cannot complete a request."""


class VoiceAudioProvider(Protocol):
    provider_name: str

    async def transcribe(self, audio: AudioInput, language: Language) -> TranscriptionResult:
        """Convert audio into text."""

    async def synthesize(self, text: str, language: Language) -> SpeechResult:
        """Convert text into playable audio."""


@dataclass
class OpenAIVoiceAudioProvider:
    api_key: str
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice_en: str = "coral"
    tts_voice_ar: str = "alloy"
    tts_format: str = "mp3"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: float = 45.0
    provider_name: str = "openai"

    async def transcribe(self, audio: AudioInput, language: Language) -> TranscriptionResult:
        if not self.api_key:
            raise VoiceProviderError("OPENAI_API_KEY is missing")
        if not audio.data:
            raise VoiceProviderError("Cannot transcribe empty audio")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.stt_model,
            "response_format": "json",
        }
        if language in {Language.ENGLISH, Language.ARABIC}:
            data["language"] = language.value

        files = {
            "file": (
                audio.filename,
                audio.data,
                audio.mime_type,
            )
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/audio/transcriptions",
                headers=headers,
                data=data,
                files=files,
            )
        if response.status_code >= 400:
            raise VoiceProviderError(f"OpenAI transcription failed with HTTP {response.status_code}")

        payload = response.json()
        text = str(payload.get("text", "")).strip()
        if not text:
            raise VoiceProviderError("OpenAI transcription returned no text")
        return TranscriptionResult(text=text, provider=self.provider_name, language=language)

    async def synthesize(self, text: str, language: Language) -> SpeechResult:
        if not self.api_key:
            raise VoiceProviderError("OPENAI_API_KEY is missing")
        if not text.strip():
            raise VoiceProviderError("Cannot synthesize empty text")

        voice = self.tts_voice_ar if language == Language.ARABIC else self.tts_voice_en
        payload = {
            "model": self.tts_model,
            "input": text,
            "voice": voice,
            "response_format": self.tts_format,
            "instructions": _speech_instructions(language),
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise VoiceProviderError(f"OpenAI speech synthesis failed with HTTP {response.status_code}")

        return SpeechResult(
            audio=response.content,
            provider=self.provider_name,
            mime_type=_mime_type_for_format(self.tts_format),
            format=self.tts_format,
        )


@dataclass
class MockVoiceAudioProvider:
    transcript: str = ""
    provider_name: str = "mock"

    async def transcribe(self, audio: AudioInput, language: Language) -> TranscriptionResult:
        text = self.transcript
        if not text:
            try:
                text = audio.data.decode("utf-8")
            except UnicodeDecodeError:
                text = "Please check my account activity from the latest statement."
        return TranscriptionResult(text=text.strip(), provider=self.provider_name, language=language)

    async def synthesize(self, text: str, language: Language) -> SpeechResult:
        return SpeechResult(
            audio=_demo_chime_wav(language),
            provider=self.provider_name,
            mime_type="audio/wav",
            format="wav",
        )


def _demo_chime_wav(language: Language) -> bytes:
    """Return a short, valid WAV cue so keyless voice remains browser-playable."""

    sample_rate = 16_000
    duration_seconds = 0.28
    frequency = 660.0 if language == Language.ARABIC else 520.0
    frame_count = int(sample_rate * duration_seconds)
    frames = bytearray()
    for index in range(frame_count):
        position = index / frame_count
        envelope = min(position / 0.08, (1.0 - position) / 0.18, 1.0)
        amplitude = int(5_500 * max(envelope, 0.0))
        sample = int(amplitude * math.sin(2.0 * math.pi * frequency * index / sample_rate))
        frames.extend(struct.pack("<h", sample))

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return output.getvalue()


def _speech_instructions(language: Language) -> str:
    if language == Language.ARABIC:
        return "Speak naturally in Arabic. Keep the tone warm, clear, and professional for a financial app."
    return "Speak naturally in English. Keep the tone warm, clear, and professional for a financial app."


def _mime_type_for_format(audio_format: str) -> str:
    normalized = audio_format.lower()
    if normalized == "mp3":
        return "audio/mpeg"
    if normalized == "wav":
        return "audio/wav"
    if normalized == "opus":
        return "audio/ogg"
    if normalized == "aac":
        return "audio/aac"
    if normalized == "flac":
        return "audio/flac"
    return "application/octet-stream"
