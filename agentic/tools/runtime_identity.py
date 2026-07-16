"""Request-scoped identity available to financial tool implementations.

The guarded agent boundary binds this context immediately around a tool call.
``ContextVar`` values propagate through ``asyncio.to_thread``, which lets the
Database-backed demo tools retain their worker-thread implementation without relying on
process-global environment variables for authenticated identity.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


_identity: ContextVar[tuple[str, str] | None] = ContextVar(
    "financial_tool_identity", default=None
)


@contextmanager
def bind_tool_identity(*, user_id: str, tenant_id: str) -> Iterator[None]:
    """Bind trusted identity for exactly one guarded external-tool invocation."""

    token = _identity.set((user_id, tenant_id))
    try:
        yield
    finally:
        _identity.reset(token)


def current_tool_identity() -> tuple[str, str] | None:
    """Return the current guarded identity, if a tool call is active."""

    return _identity.get()
