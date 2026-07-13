from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.store.postgres.aio import AsyncPostgresStore


@asynccontextmanager
async def postgres_memory_store(
    connection_string: str,
    *,
    setup: bool = False,
    index: dict | None = None,
) -> AsyncIterator[AsyncPostgresStore]:
    async with AsyncPostgresStore.from_conn_string(
        connection_string, index=index
    ) as store:
        if setup:
            await store.setup()
        yield store

