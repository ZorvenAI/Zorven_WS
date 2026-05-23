"""Integration tests for Redis prompt cache (US-004, US-011, US-012).

Requires real Redis at POI_REDIS_URL (default redis://localhost:6379/2).
"""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import DEFAULT_TTL, TenantConfigManager

from .conftest import REDIS_URL, requires_redis


@pytest.mark.integration
@requires_redis
class TestPromptCacheRedis:
    """US-004: Prompt cache against real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        # Cleanup test keys
        r = await mgr.connect()
        async for key in r.scan_iter(match="prompt:__test*"):
            await r.delete(key)
        await mgr.close()

    async def test_set_and_get_production_prompt(self, cache):
        """Set and retrieve a production prompt from real Redis."""
        await cache.set_prompt("__test-prompt", "Hello {{context.name}}", ttl=10)
        result = await cache.get_prompt("__test-prompt")
        assert result == "Hello {{context.name}}"

    async def test_set_and_get_tenant_prompt(self, cache):
        """Set and retrieve a tenant-specific prompt."""
        await cache.set_prompt(
            "__test-prompt", "Tenant template", ttl=10, tenant_id="t-int"
        )
        result = await cache.get_prompt("__test-prompt", tenant_id="t-int")
        assert result == "Tenant template"

    async def test_tenant_isolation(self, cache):
        """US-012 AC-4: Tenant A cache not readable by tenant B."""
        await cache.set_prompt(
            "__test-iso", "Tenant A", ttl=10, tenant_id="t-a"
        )
        result_b = await cache.get_prompt("__test-iso", tenant_id="t-b")
        assert result_b is None

    async def test_invalidate_prompt(self, cache):
        """Invalidation deletes all versions."""
        await cache.set_prompt("__test-inv", "prod", ttl=10)
        await cache.set_prompt(
            "__test-inv", "tenant", ttl=10, tenant_id="t-1"
        )
        deleted = await cache.invalidate_prompt("__test-inv")
        assert deleted >= 2
        assert await cache.get_prompt("__test-inv") is None

    async def test_key_naming_convention(self, cache):
        """US-004 AC-1: Keys follow prompt:<name>:production pattern."""
        await cache.set_prompt("__test-key", "value", ttl=10)
        r = await cache.connect()
        exists = await r.exists("prompt:__test-key:production")
        assert exists == 1


@pytest.mark.integration
@requires_redis
class TestOptimizationLockRedis:
    """US-004: Distributed optimization lock against real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        r = await mgr.connect()
        async for key in r.scan_iter(match="prompt:optimization:lock:__test*"):
            await r.delete(key)
        await mgr.close()

    async def test_acquire_and_release_lock(self, cache):
        """Acquire lock, verify held, release."""
        acquired = await cache.acquire_optimization_lock(
            "__test-group", "worker-1", ttl=30
        )
        assert acquired is True

        info = await cache.get_optimization_lock_info("__test-group")
        assert info["owner"] == "worker-1"

        released = await cache.release_optimization_lock(
            "__test-group", "worker-1"
        )
        assert released is True

    async def test_lock_prevents_double_acquire(self, cache):
        """Second acquire fails while lock held."""
        await cache.acquire_optimization_lock(
            "__test-double", "worker-1", ttl=30
        )
        second = await cache.acquire_optimization_lock(
            "__test-double", "worker-2", ttl=30
        )
        assert second is False
        # Cleanup
        await cache.release_optimization_lock("__test-double", "worker-1")

    async def test_wrong_owner_cannot_release(self, cache):
        """Only the owner can release the lock."""
        await cache.acquire_optimization_lock(
            "__test-owner", "worker-1", ttl=30
        )
        released = await cache.release_optimization_lock(
            "__test-owner", "worker-2"
        )
        assert released is False
        await cache.release_optimization_lock("__test-owner", "worker-1")


@pytest.mark.integration
@requires_redis
class TestTenantConfigRedis:
    """US-011: Tenant-configurable cache TTL against real Redis."""

    @pytest.fixture
    async def config(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        mgr = TenantConfigManager(cache)
        yield mgr
        r = await cache.connect()
        async for key in r.scan_iter(match="tenant:__test*"):
            await r.delete(key)
        await cache.close()

    async def test_set_and_get_ttl(self, config):
        """Set TTL, then get returns the stored value."""
        await config.set_prompt_cache_ttl("__test-tenant", 600)
        ttl = await config.get_prompt_cache_ttl("__test-tenant")
        assert ttl == 600

    async def test_missing_tenant_returns_default(self, config):
        """Missing tenant config returns 300s default."""
        ttl = await config.get_prompt_cache_ttl("__test-nonexistent")
        assert ttl == DEFAULT_TTL

    async def test_ttl_clamped_below_min(self, config):
        """Values below 10 are clamped."""
        await config.set_prompt_cache_ttl("__test-clamp", 5)
        ttl = await config.get_prompt_cache_ttl("__test-clamp")
        assert ttl == 10

    async def test_ttl_update_takes_effect(self, config):
        """US-011 AC-3: Update takes effect within one load cycle."""
        await config.set_prompt_cache_ttl("__test-update", 300)
        assert await config.get_prompt_cache_ttl("__test-update") == 300

        await config.set_prompt_cache_ttl("__test-update", 60)
        assert await config.get_prompt_cache_ttl("__test-update") == 60
