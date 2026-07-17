"""Security-evaluation fixtures that do not require infrastructure services."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide config secrets without invoking the repository-wide PostgreSQL fixture."""

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://amad:test@localhost:55432/amad")
    monkeypatch.setenv("LANGGRAPH_DATABASE_URL", "postgresql://amad:test@localhost:55432/amad")
    monkeypatch.setenv("CONFIRMATION_SIGNING_KEY", "c" * 32)
    monkeypatch.setenv("CHECKPOINT_ENCRYPTION_KEY", "e" * 32)
    monkeypatch.setenv("APP_DATA_ENCRYPTION_KEY", "d" * 32)
    monkeypatch.setenv("INTERACTION_SHARED_SECRET", "i" * 32)
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
