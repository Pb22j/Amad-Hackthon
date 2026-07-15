from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql

from agentic.api.schemas import AgenticRequest, AuthorizationContext
from agentic.config.loader import AppConfig, load_config
from agentic.persistence.database import Database


def _database_url(base_url: str, database_name: str) -> str:
    parsed = urlsplit(base_url.replace("postgresql+psycopg://", "postgresql://", 1))
    return urlunsplit(parsed._replace(path=f"/{database_name}"))


@pytest.fixture(scope="session")
def postgres_test_url() -> str:
    base_url = os.getenv(
        "TEST_POSTGRES_URL",
        "postgresql://amad:development-only-password@localhost:55432/amad",
    )
    database_name = f"amad_pytest_{uuid4().hex[:10]}"
    admin_url = _database_url(base_url, "postgres")
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    test_url = _database_url(base_url, database_name)
    yield test_url
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
        )


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, postgres_test_url: str) -> None:
    if os.getenv("RUN_LIVE_AGENT_TESTS") == "1":
        # The opt-in live matrix deliberately uses the caller's real provider,
        # PostgreSQL, encryption, and signing configuration.
        return
    monkeypatch.setenv(
        "DATABASE_URL",
        postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    monkeypatch.setenv("LANGGRAPH_DATABASE_URL", postgres_test_url)
    monkeypatch.setenv("CONFIRMATION_SIGNING_KEY", "c" * 32)
    monkeypatch.setenv("CHECKPOINT_ENCRYPTION_KEY", "e" * 32)
    monkeypatch.setenv("APP_DATA_ENCRYPTION_KEY", "d" * 32)
    monkeypatch.setenv("INTERACTION_SHARED_SECRET", "i" * 32)
    # Deterministic tests must not need provider credentials, but the opt-in
    # compatibility suite must retain the real key loaded by the caller.
    if os.getenv("RUN_REAL_MODEL_TESTS") != "1":
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.fixture
def app_config() -> AppConfig:
    config = load_config()
    return config.model_copy(
        update={
            "app": config.app.model_copy(
                update={
                    "service": config.app.service.model_copy(update={"environment": "test"}),
                    "agent": config.app.agent.model_copy(
                        update={"require_signed_interaction_requests": False}
                    ),
                }
            )
        }
    )


@pytest_asyncio.fixture
async def database(postgres_test_url: str) -> Database:
    database = Database(
        postgres_test_url.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    await database.create_schema()
    yield database
    await database.drop_schema()
    await database.dispose()


@pytest.fixture
def agentic_request() -> AgenticRequest:
    return AgenticRequest(
        request_id=uuid4(),
        session_id=uuid4(),
        user_id="user-1",
        tenant_id="tenant-1",
        language="en",
        natural_language_request="Show my current balance.",
        original_user_message="Show my current balance.",
        authorization=AuthorizationContext(
            scopes=frozenset({"financial:read", "financial:write", "investment:trade"}),
            authenticated_at=datetime.now(timezone.utc),
            assurance_level="high",
        ),
    )
