from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentic.config.loader import LLMConfig, ModelConfig, SecretsConfig
from agentic.llm.capabilities import validate_capabilities
from agentic.llm.factory import ModelFactory


def test_config_loads_separate_model_roles(app_config):
    assert app_config.llm.models["primary"].provider == "minimax"
    assert app_config.limits.task.max_tool_calls == 15
    assert "transfer_funds" in app_config.policies.financial_actions.require_exact_confirmation


def test_model_config_forbids_unknown_keys():
    with pytest.raises(ValidationError):
        ModelConfig(provider="openai", model="x", unexpected=True)


def test_llm_config_requires_critical_roles():
    with pytest.raises(ValidationError, match="missing required model roles"):
        LLMConfig(models={"primary": ModelConfig(provider="openai", model="x")})


def test_short_signing_key_is_rejected():
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        SecretsConfig(
            database_url="postgresql://localhost/amad",
            langgraph_database_url="postgresql://localhost/amad",
            confirmation_signing_key="short",
            interaction_shared_secret="i" * 32,
            application_encryption_key="d" * 32,
        )


def test_runtime_database_must_be_postgresql():
    with pytest.raises(ValidationError, match="database_url must be a PostgreSQL URL"):
        SecretsConfig(
            database_url="mysql://localhost/amad",
            langgraph_database_url="postgresql://localhost/amad",
            confirmation_signing_key="c" * 32,
            interaction_shared_secret="i" * 32,
            application_encryption_key="d" * 32,
        )


def test_provider_capability_validation_rejects_missing_capability():
    with pytest.raises(ValueError, match="lacks required capabilities"):
        validate_capabilities("anthropic", ("embeddings",))


def test_provider_capability_validation_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unsupported"):
        validate_capabilities("unknown", ())


def test_model_factory_rejects_unknown_role(app_config):
    with pytest.raises(KeyError, match="unknown model role"):
        ModelFactory(app_config.llm).create("missing")


@pytest.mark.parametrize("fallback", [("missing",), ("primary",)])
def test_llm_config_rejects_invalid_fallbacks(app_config, fallback):
    primary = app_config.llm.models["primary"].model_copy(
        update={"fallback_roles": fallback}
    )
    with pytest.raises(ValueError, match=r"fall.?back"):
        app_config.llm.__class__(
            models=app_config.llm.models | {"primary": primary}
        )


def test_production_requires_encryption_and_webhook(app_config):
    from agentic.config.loader import AppConfig

    production_app = app_config.app.model_copy(
        update={"service": app_config.app.service.model_copy(update={"environment": "production"})}
    )
    with pytest.raises(ValidationError, match="webhook"):
        AppConfig.model_validate(
            app_config.model_dump(mode="python")
            | {
                "app": production_app,
                "secrets": app_config.secrets.model_copy(
                    update={"interaction_event_webhook_url": None}
                ),
            }
        )


def test_demo_otp_adapter_cannot_be_enabled_in_production(app_config):
    from pydantic import SecretStr, ValidationError

    from agentic.config.loader import AppConfig

    production_app = app_config.app.model_copy(
        update={"service": app_config.app.service.model_copy(update={"environment": "production"})}
    )
    with pytest.raises(ValidationError, match="demo OTP confirmation adapter"):
        AppConfig.model_validate(
            app_config.model_dump(mode="python")
            | {
                "app": production_app,
                "secrets": app_config.secrets.model_copy(
                    update={
                        "interaction_event_webhook_url": "https://interaction.test/webhook",
                        "demo_confirmation_otp": SecretStr("2222"),
                    }
                ),
            }
        )


def test_yaml_root_must_be_mapping(tmp_path):
    from agentic.config.loader import _read_yaml

    path = tmp_path / "bad.yaml"
    path.write_text("- not\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="root"):
        _read_yaml(path)


def test_tool_provider_can_be_overridden_by_environment(monkeypatch):
    from agentic.config.loader import load_config

    monkeypatch.setenv("AGENTIC_TOOL_PROVIDER", "package.module:provider")
    assert load_config().app.agent.tool_provider == "package.module:provider"
