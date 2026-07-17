from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    PORT: int = 8001
    HOST: str = "0.0.0.0"

    STT_PROVIDER: str = "openai"
    LLM_PROVIDER: str = "openai"
    TTS_PROVIDER: str = "openai"

    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""

    LLM_MODEL: str = "gpt-4o-mini"
    LLM_SYSTEM_PROMPT: str = "You are a helpful and conversational AI assistant."
    REALTIME_MODEL: str = "gemini-3.1-flash-live-preview"
    REALTIME_VOICE: str = "Charon"
    REALTIME_SETUP_TIMEOUT_SECONDS: float = Field(default=30.0, ge=5.0, le=120.0)

    AGENTIC_BASE_URL: str = "http://localhost:9000"
    INTERACTION_SHARED_SECRET: str = "dummy_secret_key_123_dummy_secret_key"
    CONFIRMATION_SIGNING_KEY: str = "dummy_confirmation_key_1234567890ab"
    DEMO_CONFIRMATION_OTP: str = "1111"
    INTERACTION_DATA_ENCRYPTION_KEY: str = "dummy_interaction_data_key_12345678"
    INTERACTION_DATABASE_URL: str = (
        "postgresql://amad:development-only-password@localhost:55432/amad"
    )
    INTERACTION_TIMESTAMP_TOLERANCE_SECONDS: int = 300
    AGENTIC_TIMEOUT_SECONDS: float = Field(default=120.0, ge=1.0, le=120.0)

    DEMO_USER_ID: str = "evaluation-user"
    DEMO_TENANT_ID: str = "evaluation-tenant"
    DEMO_SCOPES: str = "financial:read,financial:write,investment:trade"
    SESSION_TTL_SECONDS: int = 3600
    VOICE_MEMORY_MAX_USER_TURNS: int = 8
    VOICE_MEMORY_MAX_ASSISTANT_TURNS: int = 3
    VOICE_MEMORY_CONTEXT_TURNS: int = 4
    VOICE_MEMORY_MAX_TEXT_CHARACTERS: int = 1000
    VOICE_MEMORY_CONTEXT_MAX_CHARACTERS: int = Field(default=2500, ge=1000, le=20_000)
    VOICE_OUTCOME_SUMMARY_MAX_CHARACTERS: int = Field(default=160, ge=120, le=1000)
    VOICE_CONTEXT_TRIGGER_TOKENS: int = Field(default=6000, ge=4000, le=120_000)
    VOICE_CONTEXT_TARGET_TOKENS: int = Field(default=2500, ge=2000, le=60_000)
    VOICE_REALTIME_MAX_TEXT_CHARACTERS: int = Field(default=8000, ge=1000, le=20_000)
    SESSION_COOKIE_SECURE: bool = False
    FRONTEND_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    MAX_AUDIO_BYTES: int = 10_000_000

    TTS_VOICE_ID: str = "alloy"
    TTS_MODEL_ID: str = "tts-1"

    CACHE_ENABLED: bool = False
    CACHE_DIR: str = "cache_dir"
    CACHE_TTL_SECONDS: int = 3600
    CACHE_MAX_ENTRIES: int = 200
    CACHE_MAX_AUDIO_BYTES: int = 5_000_000
    RATE_LIMIT_PER_MIN: int = 30
    SSL_VERIFY: bool = True
    LOG_FILE: str = ""

    @property
    def frontend_origins(self) -> list[str]:
        return [item.strip() for item in self.FRONTEND_ORIGINS.split(",") if item.strip()]

    @property
    def demo_scopes(self) -> tuple[str, ...]:
        return tuple(item.strip() for item in self.DEMO_SCOPES.split(",") if item.strip())

    @model_validator(mode="after")
    def secure_contract(self) -> "Settings":
        if len(self.INTERACTION_SHARED_SECRET.encode()) < 32:
            raise ValueError("INTERACTION_SHARED_SECRET must contain at least 32 bytes")
        if len(self.CONFIRMATION_SIGNING_KEY.encode()) < 32:
            raise ValueError("CONFIRMATION_SIGNING_KEY must contain at least 32 bytes")
        if len(self.INTERACTION_DATA_ENCRYPTION_KEY.encode()) < 32:
            raise ValueError("INTERACTION_DATA_ENCRYPTION_KEY must contain at least 32 bytes")
        if not self.INTERACTION_DATABASE_URL.startswith(
            ("postgresql://", "postgresql+psycopg://")
        ):
            raise ValueError("INTERACTION_DATABASE_URL must be a PostgreSQL URL")
        if len(self.DEMO_CONFIRMATION_OTP) != 4 or not self.DEMO_CONFIRMATION_OTP.isdigit():
            raise ValueError("DEMO_CONFIRMATION_OTP must contain exactly four digits")
        if self.ENVIRONMENT == "production" and not self.SSL_VERIFY:
            raise ValueError("SSL verification cannot be disabled in production")
        if self.ENVIRONMENT == "production":
            raise ValueError("the demo OTP confirmation adapter is not supported in production")
        if self.VOICE_CONTEXT_TARGET_TOKENS >= self.VOICE_CONTEXT_TRIGGER_TOKENS:
            raise ValueError(
                "VOICE_CONTEXT_TARGET_TOKENS must be lower than "
                "VOICE_CONTEXT_TRIGGER_TOKENS"
            )
        return self


    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env.backend",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
