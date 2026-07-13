from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Callable

from agentic.config.loader import RateLimitConfig


class RateLimitError(PermissionError):
    pass


class InMemoryRateLimiter:
    """Process-local limiter; deployments must also enforce limits at the API gateway."""

    def __init__(self, config: RateLimitConfig, *, clock: Callable[[], float] = time.monotonic):
        self.config = config
        self.clock = clock
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._user_active: dict[tuple[str, str], int] = defaultdict(int)
        self._tenant_active: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def acquire(self, *, tenant_id: str, user_id: str) -> None:
        now = self.clock()
        key = (tenant_id, user_id)
        async with self._lock:
            history = self._requests[key]
            while history and history[0] <= now - 60:
                history.popleft()
            if len(history) >= self.config.requests_per_minute:
                raise RateLimitError("request rate limit exceeded")
            if self._user_active[key] >= self.config.max_concurrent_tasks_per_user:
                raise RateLimitError("user task concurrency limit exceeded")
            if self._tenant_active[tenant_id] >= self.config.max_concurrent_tasks_per_tenant:
                raise RateLimitError("tenant task concurrency limit exceeded")
            history.append(now)
            self._user_active[key] += 1
            self._tenant_active[tenant_id] += 1

    async def release(self, *, tenant_id: str, user_id: str) -> None:
        key = (tenant_id, user_id)
        async with self._lock:
            if self._user_active[key] > 0:
                self._user_active[key] -= 1
            if self._tenant_active[tenant_id] > 0:
                self._tenant_active[tenant_id] -= 1

