"""Integration test: rate limiting with real Redis.

Verifies per-tenant rate limiting with INCR+EXPIRE pattern.
"""

from typing import Any

import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

from app.cache.redis_manager import RATE_LIMIT_TTL, RedisManager
from app.core.config import settings

pytestmark = pytest.mark.integration


class TestRateLimiting:
    """Rate limiting with real Redis."""

    async def test_allows_requests_under_limit(
        self,
        redis_manager: RedisManager,
    ) -> None:
        for i in range(settings.RATE_LIMIT_PER_MINUTE):
            allowed = await redis_manager.check_rate_limit(
                "rate-test-tenant", limit=settings.RATE_LIMIT_PER_MINUTE
            )
            assert allowed is True, f"Request {i+1} should be allowed"

    async def test_blocks_requests_over_limit(
        self,
        redis_manager: RedisManager,
    ) -> None:
        limit = settings.RATE_LIMIT_PER_MINUTE

        # Use up the limit
        for _ in range(limit):
            await redis_manager.check_rate_limit("over-limit-tenant", limit=limit)

        # Next request should be blocked
        allowed = await redis_manager.check_rate_limit("over-limit-tenant", limit=limit)
        assert allowed is False

    async def test_rate_limit_key_has_60s_ttl(
        self,
        redis_manager: RedisManager,
        redis_client: aioredis.Redis,
    ) -> None:
        await redis_manager.check_rate_limit("ttl-tenant", limit=10)

        key = "discovery:rate:ttl-tenant"
        ttl = await redis_client.ttl(key)
        assert RATE_LIMIT_TTL - 5 <= ttl <= RATE_LIMIT_TTL

    async def test_different_tenants_have_independent_limits(
        self,
        redis_manager: RedisManager,
    ) -> None:
        limit = 2

        # Exhaust tenant-A's limit
        await redis_manager.check_rate_limit("tenant-A", limit=limit)
        await redis_manager.check_rate_limit("tenant-A", limit=limit)
        blocked = await redis_manager.check_rate_limit("tenant-A", limit=limit)
        assert blocked is False

        # Tenant-B should still be allowed
        allowed = await redis_manager.check_rate_limit("tenant-B", limit=limit)
        assert allowed is True

    async def test_rate_limit_resets_after_window(
        self,
        redis_manager: RedisManager,
        redis_client: aioredis.Redis,
    ) -> None:
        limit = 1
        await redis_manager.check_rate_limit("reset-tenant", limit=limit)
        blocked = await redis_manager.check_rate_limit("reset-tenant", limit=limit)
        assert blocked is False

        # Manually flush the rate key (simulating window expiry)
        await redis_client.delete("discovery:rate:reset-tenant")

        # Now should be allowed again
        allowed = await redis_manager.check_rate_limit("reset-tenant", limit=limit)
        assert allowed is True

    async def test_rate_limit_returns_429_via_api(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        redis_client: aioredis.Redis,
    ) -> None:
        tenant_id = "rate-limited-tenant"
        headers = {"X-Tenant-ID": tenant_id}

        # Set the rate counter just below the limit
        key = f"discovery:rate:{tenant_id}"
        await redis_client.set(key, str(settings.RATE_LIMIT_PER_MINUTE), ex=60)

        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers=headers,
        )
        assert resp.status_code == 429
        assert "Rate limit" in resp.json()["detail"]
