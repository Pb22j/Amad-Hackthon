import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PORT: int = 8000
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
    REALTIME_MODEL: str = "gpt-realtime-2.1"
    REALTIME_VOICE: str = "alloy"

    AGENTIC_BASE_URL: str = "http://localhost:9000"
    INTERACTION_SHARED_SECRET: str = "dummy_secret_key_123_dummy_secret_key"

    TTS_VOICE_ID: str = "alloy"
    TTS_MODEL_ID: str = "tts-1"

    CACHE_ENABLED: bool = True
    CACHE_DIR: str = "cache_dir"
    RATE_LIMIT_PER_MIN: int = 30
    SSL_VERIFY: bool = True


    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
