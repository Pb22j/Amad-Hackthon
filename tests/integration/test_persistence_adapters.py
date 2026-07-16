from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from agentic.persistence.checkpointer import postgres_checkpointer
from agentic.persistence.store import postgres_memory_store


class FakeResource:
    def __init__(self):
        self.setup_called = False

    async def setup(self):
        self.setup_called = True


@pytest.mark.integration
async def test_encrypted_postgres_checkpointer_setup(monkeypatch):
    resource = FakeResource()

    @asynccontextmanager
    async def fake_connection(*args, **kwargs):
        assert kwargs["serde"] is not None
        yield resource

    monkeypatch.setattr(
        "agentic.persistence.checkpointer.AsyncPostgresSaver.from_conn_string",
        fake_connection,
    )
    async with postgres_checkpointer(
        "postgresql://test", encryption_key="e" * 32, setup=True
    ) as result:
        assert result is resource
    assert resource.setup_called


@pytest.mark.integration
async def test_checkpointer_rejects_invalid_encryption_key():
    with pytest.raises(ValueError, match="exactly"):
        async with postgres_checkpointer(
            "postgresql://test", encryption_key="short", setup=False
        ):
            pass


@pytest.mark.integration
async def test_postgres_store_setup(monkeypatch):
    resource = FakeResource()

    @asynccontextmanager
    async def fake_connection(*args, **kwargs):
        assert kwargs["index"] == {"dims": 3}
        yield resource

    monkeypatch.setattr(
        "agentic.persistence.store.AsyncPostgresStore.from_conn_string", fake_connection
    )
    async with postgres_memory_store(
        "postgresql://test", setup=True, index={"dims": 3}
    ) as result:
        assert result is resource
    assert resource.setup_called

