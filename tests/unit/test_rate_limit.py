import pytest

from agentic.config.loader import RateLimitConfig
from agentic.security.rate_limit import InMemoryRateLimiter, RateLimitError


@pytest.mark.asyncio
async def test_rate_and_user_concurrency_limits():
    now = [100.0]
    limiter = InMemoryRateLimiter(
        RateLimitConfig(
            requests_per_minute=2,
            max_concurrent_tasks_per_user=1,
            max_concurrent_tasks_per_tenant=2,
        ),
        clock=lambda: now[0],
    )
    await limiter.acquire(tenant_id="t", user_id="u")
    with pytest.raises(RateLimitError, match="user task concurrency"):
        await limiter.acquire(tenant_id="t", user_id="u")
    await limiter.release(tenant_id="t", user_id="u")
    await limiter.acquire(tenant_id="t", user_id="u")
    await limiter.release(tenant_id="t", user_id="u")
    with pytest.raises(RateLimitError, match="request rate"):
        await limiter.acquire(tenant_id="t", user_id="u")
    now[0] += 61
    await limiter.acquire(tenant_id="t", user_id="u")
    await limiter.release(tenant_id="t", user_id="u")


@pytest.mark.asyncio
async def test_tenant_concurrency_limit():
    limiter = InMemoryRateLimiter(
        RateLimitConfig(
            requests_per_minute=10,
            max_concurrent_tasks_per_user=2,
            max_concurrent_tasks_per_tenant=1,
        )
    )
    await limiter.acquire(tenant_id="t", user_id="u1")
    with pytest.raises(RateLimitError, match="tenant task concurrency"):
        await limiter.acquire(tenant_id="t", user_id="u2")
    await limiter.release(tenant_id="t", user_id="u1")

