"""Integration tests for Redis cache lifecycle via testcontainers (US-059).

Tests prompt cache set/get/invalidate, tenant isolation, optimization
locks, and tenant config against a real Redis container.
"""

import asyncio
import os

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import TenantConfigManager

TEST_PREFIX = "__tc_redis_"


@pytest.mark.integration
class TestRedisCacheLifecycleTC:
    """Redis cache lifecycle via testcontainers."""

    @pytest.fixture
    async def cache(self):
        url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "redis://localhost:6379/2")
        mgr = PromptCacheManager(redis_url=url)
        await mgr.connect()
        yield mgr
        r = await mgr.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        async for key in r.scan_iter(match=f"prompt:optimization:lock:{TEST_PREFIX}*"):
            await r.delete(key)
        async for key in r.scan_iter(match=f"tenant:{TEST_PREFIX}*"):
            await r.delete(key)
        await mgr.close()

    async def test_set_get_invalidate_cycle(self, cache):
        """Full lifecycle: set → get (hit) → invalidate → get (miss)."""
        key = f"{TEST_PREFIX}lifecycle"
        await cache.set_prompt(key, "cached template", ttl=30)
        assert await cache.get_prompt(key) == "cached template"
        await cache.invalidate_prompt(key)
        assert await cache.get_prompt(key) is None

    async def test_ttl_expiry(self, cache):
        """Set with 1s TTL, wait, verify expired."""
        key = f"{TEST_PREFIX}ttl-expiry"
        await cache.set_prompt(key, "short lived", ttl=1)
        assert await cache.get_prompt(key) == "short lived"
        await asyncio.sleep(2)
        assert await cache.get_prompt(key) is None

    async def test_tenant_isolation_no_cross_read(self, cache):
        """Tenant A can't read tenant B's cached prompt."""
        key = f"{TEST_PREFIX}isolation"
        await cache.set_prompt(key, "Tenant A data", ttl=30, tenant_id="t-a")
        result = await cache.get_prompt(key, tenant_id="t-b")
        assert result is None

    async def test_invalidate_deletes_all_variants(self, cache):
        """Invalidate removes production + tenant keys."""
        key = f"{TEST_PREFIX}inv-all"
        await cache.set_prompt(key, "prod", ttl=30)
        await cache.set_prompt(key, "tenant-1", ttl=30, tenant_id="t-1")
        deleted = await cache.invalidate_prompt(key)
        assert deleted >= 2
        assert await cache.get_prompt(key) is None
        assert await cache.get_prompt(key, tenant_id="t-1") is None

    async def test_optimization_lock_lifecycle(self, cache):
        """Acquire → verify held → release → verify released."""
        group = f"{TEST_PREFIX}lock-lc"
        acquired = await cache.acquire_optimization_lock(group, "worker-1", ttl=30)
        assert acquired is True
        info = await cache.get_optimization_lock_info(group)
        assert info["owner"] == "worker-1"
        released = await cache.release_optimization_lock(group, "worker-1")
        assert released is True

    async def test_optimization_lock_owner_safety(self, cache):
        """Wrong owner cannot release the lock."""
        group = f"{TEST_PREFIX}lock-owner"
        await cache.acquire_optimization_lock(group, "worker-1", ttl=30)
        released = await cache.release_optimization_lock(group, "worker-2")
        assert released is False
        await cache.release_optimization_lock(group, "worker-1")

    async def test_optimization_lock_prevents_double_acquire(self, cache):
        """Second acquire by different owner fails."""
        group = f"{TEST_PREFIX}lock-double"
        await cache.acquire_optimization_lock(group, "worker-1", ttl=30)
        second = await cache.acquire_optimization_lock(group, "worker-2", ttl=30)
        assert second is False
        await cache.release_optimization_lock(group, "worker-1")

    async def test_tenant_config_set_and_get_ttl(self, cache):
        """Set tenant TTL, retrieve matches."""
        config = TenantConfigManager(cache)
        await config.set_prompt_cache_ttl(f"{TEST_PREFIX}tenant-ttl", 600)
        ttl = await config.get_prompt_cache_ttl(f"{TEST_PREFIX}tenant-ttl")
        assert ttl == 600

    async def test_tenant_config_clamp_enforced(self, cache):
        """TTL below 10 clamped to 10."""
        config = TenantConfigManager(cache)
        await config.set_prompt_cache_ttl(f"{TEST_PREFIX}tenant-clamp", 5)
        ttl = await config.get_prompt_cache_ttl(f"{TEST_PREFIX}tenant-clamp")
        assert ttl == 10
