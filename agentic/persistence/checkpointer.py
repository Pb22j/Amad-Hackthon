"""Encrypted PostgreSQL LangGraph checkpointer construction and serialization."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


@asynccontextmanager
async def postgres_checkpointer(
    connection_string: str,
    *,
    encryption_key: str,
    setup: bool = False,
) -> AsyncIterator[AsyncPostgresSaver]:
    key = encryption_key.encode("utf-8")
    if len(key) not in (16, 24, 32):
        raise ValueError("checkpoint encryption key must be exactly 16, 24, or 32 bytes")
    # Prevent unsafe fallback deserialization if a checkpoint database is compromised.
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    safe_serde = JsonPlusSerializer(
        allowed_msgpack_modules={
            ("agentic.agent.report", "AgentReport"),
            ("agentic.agent.report", "ActionReceipt"),
        }
    )
    serde = EncryptedSerializer.from_pycryptodome_aes(serde=safe_serde, key=key)
    async with AsyncPostgresSaver.from_conn_string(
        connection_string, serde=serde
    ) as checkpointer:
        if setup:
            await checkpointer.setup()
        yield checkpointer
