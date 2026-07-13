from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Protocol

import httpx

from agentic.api.schemas import AgentEvent


class EventPublisher(Protocol):
    async def publish(self, event: AgentEvent) -> None: ...


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []
        self._lock = asyncio.Lock()

    async def publish(self, event: AgentEvent) -> None:
        async with self._lock:
            self.events.append(event)


class WebhookEventPublisher:
    def __init__(
        self,
        url: str,
        secret: str | bytes,
        *,
        client: httpx.AsyncClient | None = None,
        attempts: int = 3,
    ) -> None:
        self.url = url
        self.secret = secret.encode() if isinstance(secret, str) else secret
        self.client = client or httpx.AsyncClient(timeout=10)
        self.attempts = attempts
        self._owns_client = client is None

    async def publish(self, event: AgentEvent) -> None:
        body = event.model_dump_json().encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret, timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                response = await self.client.post(
                    self.url,
                    content=body,
                    headers={
                        "content-type": "application/json",
                        "x-agentic-timestamp": timestamp,
                        "x-agentic-signature": signature,
                    },
                )
                response.raise_for_status()
                return
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt + 1 < self.attempts:
                    await asyncio.sleep(0.05 * (2**attempt))
        raise RuntimeError("failed to deliver agent event") from last_error

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
