"""Strict, immutable configuration models and YAML/environment loader.

Operational settings live in reviewable YAML files while secrets remain in the
environment. Unknown fields are rejected to catch misspellings and obsolete
settings during startup rather than silently weakening a policy.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from agentic.config.environment import load_backend_environment


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelConfig(StrictModel):
    provider: str
    model: str
    temperature: float = Field(default=0, ge=0, le=2)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=1, ge=0, le=5)
    required_capabilities: tuple[str, ...] = ()
    fallback_roles: tuple[str, ...] = ()
    input_cost_per_million: float = Field(default=0, ge=0)
    output_cost_per_million: float = Field(default=0, ge=0)


class LLMConfig(StrictModel):
    models: dict[str, ModelConfig]

    @field_validator("models")
    @classmethod
    def required_roles(cls, value: dict[str, ModelConfig]) -> dict[str, ModelConfig]:
        missing = {
            "primary",
            "intent_classifier",
            "guardrail",
            "summarizer",
            "memory_extractor",
        } - value.keys()
        if missing:
            raise ValueError(f"missing required model roles: {sorted(missing)}")
        return value

    @model_validator(mode="after")
    def valid_fallback_graph(self) -> LLMConfig:
        for role, item in self.models.items():
            unknown = set(item.fallback_roles) - self.models.keys()
            if unknown:
                raise ValueError(
                    f"model role {role!r} references unknown fallbacks: {sorted(unknown)}"
                )
            if role in item.fallback_roles:
                raise ValueError(f"model role {role!r} cannot fall back to itself")
        return self


class ServiceConfig(StrictModel):
    name: str
    environment: Literal["development", "test", "staging", "production"]
    api_version: str = "v1"
    debug: bool = False


class AgentConfig(StrictModel):
    supported_languages: tuple[Literal["en", "ar"], ...] = ("en", "ar")
    default_language: Literal["en", "ar"] = "en"
    semantic_memory_enabled: bool = False
    require_signed_interaction_requests: bool = True
    emit_progress_events: bool = True
    tool_provider: str | None = None


class DatabaseConfig(StrictModel):
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=20, ge=0, le=200)
    pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    echo: bool = False


class AgentFileConfig(StrictModel):
    service: ServiceConfig
    agent: AgentConfig
    database: DatabaseConfig


class TaskLimits(StrictModel):
    max_runtime_seconds: int = Field(ge=1, le=3600)
    max_model_calls: int = Field(ge=1, le=100)
    max_tool_calls: int = Field(ge=1, le=100)
    max_clarification_rounds: int = Field(ge=1, le=10)
    max_tool_result_bytes: int = Field(ge=1024, le=10_000_000)
    max_context_tokens: int = Field(ge=1000, le=2_000_000)
    max_request_characters: int = Field(ge=100, le=1_000_000)


class MemoryLimits(StrictModel):
    recent_messages: int = Field(ge=1, le=200)
    max_items_per_session: int = Field(default=50, ge=5, le=500)
    max_items_per_type: int = Field(default=5, ge=1, le=50)
    max_value_characters: int = Field(default=4000, ge=100, le=50_000)
    task_checkpoint_ttl_days: int = Field(ge=1, le=3650)
    semantic_top_k: int = Field(ge=1, le=100)
    minimum_similarity: float = Field(ge=0, le=1)


class RetryLimits(StrictModel):
    model_attempts: int = Field(ge=1, le=10)
    read_tool_attempts: int = Field(ge=1, le=10)
    write_tool_attempts: int = Field(ge=1, le=3)


class ReportLimits(StrictModel):
    max_actions: int = Field(ge=1, le=10)
    max_summary_characters: int = Field(ge=50, le=2000)


class RateLimitConfig(StrictModel):
    requests_per_minute: int = Field(ge=1, le=10_000)
    max_concurrent_tasks_per_user: int = Field(ge=1, le=100)
    max_concurrent_tasks_per_tenant: int = Field(ge=1, le=10_000)


class LimitsConfig(StrictModel):
    task: TaskLimits
    memory: MemoryLimits
    retries: RetryLimits
    report: ReportLimits
    rate_limit: RateLimitConfig


class FinancialActionPolicy(StrictModel):
    require_exact_confirmation: frozenset[str] = frozenset()
    require_authoritative_receipt: frozenset[str] = frozenset()


class SecurityPolicy(StrictModel):
    reject_cross_user_requests: bool = True
    reject_credential_requests: bool = True
    reject_policy_bypass: bool = True
    redact_sensitive_logs: bool = True
    tool_results_are_untrusted: bool = True
    blocked_intents: frozenset[str] = frozenset()


class MemoryPolicyConfig(StrictModel):
    allowed_types: frozenset[str]
    forbidden_key_fragments: frozenset[str]


class PoliciesConfig(StrictModel):
    financial_actions: FinancialActionPolicy
    security: SecurityPolicy
    memory: MemoryPolicyConfig


class ToolFileConfig(StrictModel):
    tools: dict[str, dict[str, Any]] = {}


class SecretsConfig(StrictModel):
    database_url: SecretStr
    langgraph_database_url: SecretStr
    confirmation_signing_key: SecretStr
    checkpoint_encryption_key: SecretStr | None = None
    interaction_shared_secret: SecretStr
    interaction_event_webhook_url: str | None = None
    application_encryption_key: SecretStr
    demo_confirmation_otp: SecretStr = SecretStr("1111")

    @model_validator(mode="after")
    def secure_keys(self) -> "SecretsConfig":
        for name in ("database_url", "langgraph_database_url"):
            value = getattr(self, name).get_secret_value()
            if not value.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError(f"{name} must be a PostgreSQL URL")
        for name in (
            "confirmation_signing_key",
            "interaction_shared_secret",
            "application_encryption_key",
        ):
            value = getattr(self, name).get_secret_value()
            if len(value.encode()) < 32:
                raise ValueError(f"{name} must contain at least 32 bytes")
        otp = self.demo_confirmation_otp.get_secret_value()
        if len(otp) != 4 or not otp.isdigit():
            raise ValueError("demo_confirmation_otp must contain exactly four digits")
        return self


class AppConfig(StrictModel):
    llm: LLMConfig
    app: AgentFileConfig
    limits: LimitsConfig
    policies: PoliciesConfig
    tools: ToolFileConfig
    secrets: SecretsConfig

    @model_validator(mode="after")
    def production_requirements(self) -> "AppConfig":
        if self.app.service.environment == "production":
            if not self.secrets.checkpoint_encryption_key:
                raise ValueError("checkpoint encryption is required in production")
            if not self.secrets.interaction_event_webhook_url:
                raise ValueError("interaction event webhook is required in production")
            raise ValueError(
                "the demo OTP confirmation adapter is not supported in production"
            )
        return self


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"configuration root must be an object: {path}")
    return data


def load_config(config_dir: str | Path | None = None) -> AppConfig:
    """Load all configuration files and required secret environment values."""

    load_backend_environment()
    root = Path(config_dir) if config_dir else Path(__file__).resolve().parent
    secrets = SecretsConfig(
        database_url=os.environ["DATABASE_URL"],
        langgraph_database_url=os.environ["LANGGRAPH_DATABASE_URL"],
        confirmation_signing_key=os.environ["CONFIRMATION_SIGNING_KEY"],
        checkpoint_encryption_key=os.getenv("CHECKPOINT_ENCRYPTION_KEY"),
        interaction_shared_secret=os.environ["INTERACTION_SHARED_SECRET"],
        interaction_event_webhook_url=os.getenv("INTERACTION_EVENT_WEBHOOK_URL"),
        application_encryption_key=os.environ["APP_DATA_ENCRYPTION_KEY"],
        demo_confirmation_otp=os.getenv("DEMO_CONFIRMATION_OTP", "1111"),
    )
    app_file = AgentFileConfig.model_validate(_read_yaml(root / "agent.yaml"))
    if provider := os.getenv("AGENTIC_TOOL_PROVIDER"):
        app_file = app_file.model_copy(
            update={"agent": app_file.agent.model_copy(update={"tool_provider": provider})}
        )
    return AppConfig(
        llm=LLMConfig.model_validate(_read_yaml(root / "llm.yaml")),
        app=app_file,
        limits=LimitsConfig.model_validate(_read_yaml(root / "limits.yaml")),
        policies=PoliciesConfig.model_validate(_read_yaml(root / "policies.yaml")),
        tools=ToolFileConfig.model_validate(_read_yaml(root / "tools.yaml")),
        secrets=secrets,
    )


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Return the process-wide immutable configuration instance."""

    return load_config()
