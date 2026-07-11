"""Environment-backed settings for provider wiring."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when Nafi cannot start safely with the selected configuration."""


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    chat_model: str = "gpt-5.6-luna"
    chat_timeout_ms: int = 30_000
    realtime_model: str = "gpt-realtime-2.1"
    realtime_voice: str = "marin"


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    intent_model: str = ""
    chat_model: str = ""
    reasoning_model: str = ""


@dataclass(frozen=True)
class PersonaPlexSettings:
    api_key: str = ""
    agent_id: str = ""
    url: str = "wss://localhost:8998"
    voice: str = "NATF2.pt"
    text_prompt: str = (
        "You are a warm financial voice assistant. Speak naturally and never expose internal details."
    )


@dataclass(frozen=True)
class ArabicVoiceSettings:
    provider: str = ""
    api_key: str = ""


@dataclass(frozen=True)
class VoiceAudioSettings:
    provider: str = "auto"
    openai_api_key: str = ""
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice_en: str = "coral"
    tts_voice_ar: str = "alloy"
    tts_format: str = "mp3"


@dataclass(frozen=True)
class SecuritySettings:
    guard_provider: str = "deterministic"
    guard_model: str = ""
    guard_required: bool = False
    guard_timeout_seconds: float = 20.0


@dataclass(frozen=True)
class AgenticSettings:
    base_url: str = "http://127.0.0.1:8090"
    request_path: str = "/agentic/request"
    webhook_secret: str = ""
    notification_secret: str = ""


@dataclass(frozen=True)
class RuntimeSettings:
    host: str = "127.0.0.1"
    port: int = 8088
    use_mock_agentic: bool = False


@dataclass(frozen=True)
class InteractionSettings:
    runtime: RuntimeSettings
    openai: OpenAISettings
    openrouter: OpenRouterSettings
    personaplex: PersonaPlexSettings
    arabic_voice: ArabicVoiceSettings
    voice_audio: VoiceAudioSettings
    security: SecuritySettings
    agentic: AgenticSettings

    @classmethod
    def from_env(cls) -> "InteractionSettings":
        openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        settings = cls(
            runtime=RuntimeSettings(
                host=os.getenv("USER_INTERACTION_HOST", "127.0.0.1"),
                port=_env_int("USER_INTERACTION_PORT", default=8088),
                use_mock_agentic=_env_bool("USER_INTERACTION_USE_MOCK_AGENTIC", default=False),
            ),
            openai=OpenAISettings(
                api_key=openai_api_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip(),
                chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna").strip(),
                chat_timeout_ms=_env_int("OPENAI_CHAT_TIMEOUT_MS", default=30_000),
                realtime_model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1").strip(),
                realtime_voice=os.getenv("OPENAI_REALTIME_VOICE", "marin").strip(),
            ),
            openrouter=OpenRouterSettings(
                api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
                base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip(),
                intent_model=os.getenv("OPENROUTER_INTENT_MODEL", "").strip(),
                chat_model=os.getenv("OPENROUTER_CHAT_MODEL", "").strip(),
                reasoning_model=os.getenv("OPENROUTER_REASONING_MODEL", "").strip(),
            ),
            personaplex=PersonaPlexSettings(
                api_key=os.getenv("PERSONAPLEX_API_KEY", ""),
                agent_id=os.getenv("PERSONAPLEX_AGENT_ID", ""),
                url=os.getenv("PERSONAPLEX_URL", "wss://localhost:8998"),
                voice=os.getenv("PERSONAPLEX_VOICE", "NATF2.pt"),
                text_prompt=os.getenv(
                    "PERSONAPLEX_TEXT_PROMPT",
                    "You are a warm financial voice assistant. Speak naturally and never expose internal details.",
                ),
            ),
            arabic_voice=ArabicVoiceSettings(
                provider=os.getenv("ARABIC_VOICE_PROVIDER", "openai"),
                api_key=os.getenv("ARABIC_VOICE_API_KEY", ""),
            ),
            voice_audio=VoiceAudioSettings(
                provider=os.getenv("VOICE_AUDIO_PROVIDER", "auto").strip().lower(),
                openai_api_key=openai_api_key,
                stt_model=os.getenv("VOICE_STT_MODEL", "gpt-4o-mini-transcribe"),
                tts_model=os.getenv("VOICE_TTS_MODEL", "gpt-4o-mini-tts"),
                tts_voice_en=os.getenv("VOICE_TTS_VOICE_EN", "coral"),
                tts_voice_ar=os.getenv("VOICE_TTS_VOICE_AR", "alloy"),
                tts_format=os.getenv("VOICE_TTS_FORMAT", "mp3"),
            ),
            security=SecuritySettings(
                guard_provider=os.getenv("SECURITY_GUARD_PROVIDER", "deterministic").strip().lower(),
                guard_model=os.getenv(
                    "SECURITY_GUARD_MODEL",
                    os.getenv("OPENROUTER_INTENT_MODEL", ""),
                ),
                guard_required=_env_bool("SECURITY_GUARD_REQUIRED", default=False),
                guard_timeout_seconds=_env_float("SECURITY_GUARD_TIMEOUT_SECONDS", default=20.0),
            ),
            agentic=AgenticSettings(
                base_url=os.getenv("AGENTIC_BASE_URL", "http://127.0.0.1:8090").strip(),
                request_path=os.getenv("AGENTIC_REQUEST_PATH", "/agentic/request"),
                webhook_secret=os.getenv("AGENTIC_WEBHOOK_SECRET", ""),
                notification_secret=os.getenv("AGENTIC_NOTIFICATION_SECRET", ""),
            ),
        )
        settings.validate()
        return settings

    @property
    def resolved_voice_provider(self) -> str:
        if self.voice_audio.provider == "auto":
            return "openai" if self.openai.api_key else "mock"
        if self.voice_audio.provider == "openai" and not self.openai.api_key:
            return "mock"
        return self.voice_audio.provider

    @property
    def configuration_warnings(self) -> tuple[str, ...]:
        warnings: list[str] = []
        if self.voice_audio.provider == "openai" and not self.openai.api_key:
            warnings.append("OPENAI_API_KEY is empty; voice is using the offline mock provider")
        if self.security.guard_provider == "openrouter" and not self.openrouter.api_key:
            warnings.append("OPENROUTER_API_KEY is empty; security uses deterministic fallback")
        return tuple(warnings)

    def validate(self) -> None:
        errors: list[str] = []
        if not self.runtime.host.strip():
            errors.append("USER_INTERACTION_HOST cannot be empty")
        if not 1 <= self.runtime.port <= 65_535:
            errors.append("USER_INTERACTION_PORT must be between 1 and 65535")
        if self.voice_audio.provider not in {"auto", "mock", "openai"}:
            errors.append("VOICE_AUDIO_PROVIDER must be auto, mock, or openai")
        if self.voice_audio.tts_format.lower() not in {"mp3", "wav", "opus", "aac", "flac"}:
            errors.append("VOICE_TTS_FORMAT must be mp3, wav, opus, aac, or flac")
        if self.security.guard_provider not in {"deterministic", "none", "openrouter"}:
            errors.append("SECURITY_GUARD_PROVIDER must be deterministic, none, or openrouter")
        if self.security.guard_timeout_seconds <= 0:
            errors.append("SECURITY_GUARD_TIMEOUT_SECONDS must be greater than zero")
        if self.security.guard_required and (
            self.security.guard_provider != "openrouter"
            or not self.openrouter.api_key
            or not self.security.guard_model
        ):
            errors.append(
                "SECURITY_GUARD_REQUIRED=true requires SECURITY_GUARD_PROVIDER=openrouter, "
                "OPENROUTER_API_KEY, and SECURITY_GUARD_MODEL"
            )
        if not self.runtime.use_mock_agentic and not _is_http_url(self.agentic.base_url):
            errors.append("AGENTIC_BASE_URL must be an http(s) URL when mock agentic is disabled")
        if not _is_http_url(self.openai.base_url):
            errors.append("OPENAI_BASE_URL must be an http(s) URL")
        if not _is_http_url(self.openrouter.base_url):
            errors.append("OPENROUTER_BASE_URL must be an http(s) URL")
        if self.openai.chat_timeout_ms < 1_000 or self.openai.chat_timeout_ms > 120_000:
            errors.append("OPENAI_CHAT_TIMEOUT_MS must be between 1000 and 120000")
        if errors:
            raise ConfigurationError("Invalid Nafi configuration:\n- " + "\n- ".join(errors))


def _env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false, got {raw_value!r}")


def _env_int(name: str, *, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw_value!r}") from exc


def _env_float(name: str, *, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw_value!r}") from exc


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
