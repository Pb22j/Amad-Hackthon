from __future__ import annotations

import sys
from contextlib import asynccontextmanager

import pytest

from agentic.cli import main
from agentic.config.loader import ModelConfig
from agentic.llm.factory import ModelFactory


def test_model_factory_builds_openrouter_and_caches(monkeypatch, app_config):
    calls = []
    sentinel = object()

    def fake_init(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    # Explicitly set primary provider to openrouter for this test
    primary = app_config.llm.models["primary"].model_copy(
        update={"provider": "openrouter", "model": "openai/gpt-4.1-mini"}
    )
    config_llm = app_config.llm.model_copy(
        update={"models": app_config.llm.models | {"primary": primary}}
    )

    monkeypatch.setattr("agentic.llm.factory.init_chat_model", fake_init)
    factory = ModelFactory(config_llm)
    assert factory.create("primary") is sentinel
    assert factory.create("primary") is sentinel
    assert len(calls) == 1
    assert calls[0][1]["base_url"] == "https://openrouter.ai/api/v1"


def test_model_factory_builds_configured_fallbacks(monkeypatch, app_config):
    sentinel = object()
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr(
        "agentic.llm.factory.init_chat_model", lambda *args, **kwargs: sentinel
    )
    primary = app_config.llm.models["primary"].model_copy(
        update={"fallback_roles": ("guardrail",)}
    )
    config = app_config.llm.model_copy(
        update={"models": app_config.llm.models | {"primary": primary}}
    )

    assert ModelFactory(config).create_fallbacks("primary") == [sentinel]


def test_model_factory_rejects_unknown_fallback_source(app_config):
    with pytest.raises(KeyError, match="unknown model role"):
        ModelFactory(app_config.llm).create_fallbacks("missing")


@pytest.mark.parametrize(
    ("provider", "key_name"),
    [("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")],
)
def test_model_factory_builds_direct_providers(
    monkeypatch, app_config, provider, key_name
):
    monkeypatch.setenv(key_name, "key")
    calls = []
    monkeypatch.setattr(
        "agentic.llm.factory.init_chat_model",
        lambda *args, **kwargs: calls.append((args, kwargs)) or object(),
    )
    config = app_config.llm.model_copy(
        update={
            "models": app_config.llm.models
            | {
                "direct": ModelConfig(
                    provider=provider,
                    model="model",
                    required_capabilities=("async",),
                )
            }
        }
    )
    ModelFactory(config).create("direct")
    assert calls[0][1]["model_provider"] == provider


@pytest.mark.parametrize(
    ("provider", "key_name"),
    [("openrouter", "OPENROUTER_API_KEY"), ("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY")],
)
def test_model_factory_requires_provider_key(monkeypatch, app_config, provider, key_name):
    monkeypatch.delenv(key_name, raising=False)
    config = app_config.llm.model_copy(
        update={
            "models": app_config.llm.models
            | {
                "direct": ModelConfig(
                    provider=provider,
                    model="model",
                    required_capabilities=("async",),
                )
            }
        }
    )
    with pytest.raises(RuntimeError, match=key_name):
        ModelFactory(config).create("direct")


def test_eval_cli_exits_successfully(monkeypatch, capsys, app_config):
    monkeypatch.setattr("agentic.cli.load_config", lambda: app_config)
    monkeypatch.setattr(sys, "argv", ["amad-agent", "eval-security"])
    main()
    assert '"failures": []' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_setup_langgraph_cli_uses_both_stores(monkeypatch, app_config):
    entered = []

    @asynccontextmanager
    async def fake_checkpointer(*args, **kwargs):
        entered.append(("checkpointer", kwargs["setup"]))
        yield object()

    @asynccontextmanager
    async def fake_store(*args, **kwargs):
        entered.append(("store", kwargs["setup"]))
        yield object()

    monkeypatch.setattr("agentic.cli.load_config", lambda: app_config)
    monkeypatch.setattr("agentic.cli.postgres_checkpointer", fake_checkpointer)
    monkeypatch.setattr("agentic.cli.postgres_memory_store", fake_store)
    from agentic.cli import setup_langgraph

    await setup_langgraph()
    assert entered == [("checkpointer", True), ("store", True)]


def test_setup_cli_command_dispatches(monkeypatch):
    called = []

    async def fake_setup():
        called.append(True)

    monkeypatch.setattr("agentic.cli.setup_langgraph", fake_setup)
    monkeypatch.setattr(sys, "argv", ["amad-agent", "setup-langgraph"])
    main()
    assert called == [True]


@pytest.mark.asyncio
async def test_cleanup_retention_deletes_checkpoints(monkeypatch, capsys, app_config):
    deleted_threads = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *args):
            return False

    class FakeDatabase:
        def __init__(self, *args, **kwargs):
            self.disposed = False

        def session(self):
            return FakeSessionContext()

        async def dispose(self):
            self.disposed = True

    class FakeRetention:
        def __init__(self, session):
            pass

        async def cleanup_expired(self):
            return ["task-1", "task-2"], 3

    class FakeCheckpointer:
        async def adelete_thread(self, task_id):
            deleted_threads.append(task_id)

    @asynccontextmanager
    async def fake_checkpointer(*args, **kwargs):
        yield FakeCheckpointer()

    monkeypatch.setattr("agentic.cli.load_config", lambda: app_config)
    monkeypatch.setattr("agentic.cli.Database", FakeDatabase)
    monkeypatch.setattr("agentic.cli.RetentionRepository", FakeRetention)
    monkeypatch.setattr("agentic.cli.postgres_checkpointer", fake_checkpointer)
    from agentic.cli import cleanup_retention

    await cleanup_retention()
    assert deleted_threads == ["task-1", "task-2"]
    assert "deleted_memories=3" in capsys.readouterr().out


def test_cleanup_cli_command_dispatches(monkeypatch):
    called = []

    async def fake_cleanup():
        called.append(True)

    monkeypatch.setattr("agentic.cli.cleanup_retention", fake_cleanup)
    monkeypatch.setattr(sys, "argv", ["amad-agent", "cleanup-retention"])
    main()
    assert called == [True]
