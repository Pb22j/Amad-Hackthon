from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from agentic.api.schemas import AgenticRequest, AuthorizationContext
from agentic.config.loader import AppConfig, load_config
from agentic.persistence.database import Database


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("LANGGRAPH_DATABASE_URL", "postgresql://unused")
    monkeypatch.setenv("CONFIRMATION_SIGNING_KEY", "c" * 32)
    monkeypatch.setenv("CHECKPOINT_ENCRYPTION_KEY", "e" * 32)
    monkeypatch.setenv("APP_DATA_ENCRYPTION_KEY", "d" * 32)
    monkeypatch.setenv("INTERACTION_SHARED_SECRET", "i" * 32)
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
async def database() -> Database:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    yield database
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
