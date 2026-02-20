"""Integration test: multi-tenant safety.

Verifies that rate limits, cache keys, and tenant propagation
are properly isolated per tenant.
"""

from typing import Any

import pytest
import redis.asyncio as aioredis
from httpx import AsyncClient

from app.cache.redis_manager import RedisManager

pytestmark = pytest.mark.integration


class TestTenantIsolation:
    """Multi-tenant safety with real Redis."""

    async def test_rate_limits_independent_per_tenant(
        self,
        redis_manager: RedisManager,
    ) -> None:
        limit = 2

        # Exhaust tenant-A
        for _ in range(limit):
            await redis_manager.check_rate_limit("tenant-A", limit=limit)
        blocked = await redis_manager.check_rate_limit("tenant-A", limit=limit)
        assert blocked is False

        # Tenant-B unaffected
        allowed = await redis_manager.check_rate_limit("tenant-B", limit=limit)
        assert allowed is True

    async def test_rate_limit_keys_include_tenant_id(
        self,
        redis_manager: RedisManager,
        redis_client: aioredis.Redis,
    ) -> None:
        await redis_manager.check_rate_limit("tenant-xyz", limit=10)

        key = "discovery:rate:tenant-xyz"
        exists = await redis_client.exists(key)
        assert exists == 1

    async def test_tenant_id_propagated_in_api(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
        redis_client: aioredis.Redis,
    ) -> None:
        tenant_id = "propagation-test-tenant"
        resp = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers={"X-Tenant-ID": tenant_id},
        )
        assert resp.status_code == 200

        # Verify rate limit key was created for this tenant
        key = f"discovery:rate:{tenant_id}"
        exists = await redis_client.exists(key)
        assert exists == 1

    async def test_different_tenants_both_succeed(
        self,
        app_with_redis: AsyncClient,
        valid_execute_payload: dict[str, Any],
    ) -> None:
        resp_a = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers={"X-Tenant-ID": "tenant-alpha"},
        )
        resp_b = await app_with_redis.post(
            "/v1/execute",
            json=valid_execute_payload,
            headers={"X-Tenant-ID": "tenant-beta"},
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
