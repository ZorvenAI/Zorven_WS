"""Tests for tenant override resolution and isolation using real Redis (US-012)."""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.services.prompt_loader import ZorvenPromptLoader
from .conftest import REDIS_URL, requires_redis

TEST_PREFIX = "__test_iso_"


@requires_redis
class TestCacheFallthrough:
    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        ldr = ZorvenPromptLoader(cache)
        yield ldr
        r = await cache.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        await cache.close()

    async def test_tenant_miss_falls_to_global(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}fall", "Global production", ttl=10
        )
        result = await loader.load(f"{TEST_PREFIX}fall", tenant_id="t-miss")
        assert result == "Global production"

    async def test_tenant_hit_skips_global(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}hit", "Global", ttl=10
        )
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}hit", "Tenant", ttl=10, tenant_id="t-1"
        )
        result = await loader.load(f"{TEST_PREFIX}hit", tenant_id="t-1")
        assert result == "Tenant"

    async def test_no_tenant_checks_global_only(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}glob", "Global", ttl=10
        )
        result = await loader.load(f"{TEST_PREFIX}glob")
        assert result == "Global"


@requires_redis
class TestTenantIsolation:
    def test_cache_keys_are_tenant_scoped(self):
        key_t1 = PromptCacheManager._prompt_key("test", "t-1")
        key_t2 = PromptCacheManager._prompt_key("test", "t-2")
        key_global = PromptCacheManager._prompt_key("test")
        assert key_t1 != key_t2
        assert key_t1 != key_global
        assert "t-1" in key_t1
        assert "production" in key_global

    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        ldr = ZorvenPromptLoader(cache)
        yield ldr
        r = await cache.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        await cache.close()

    async def test_tenant_a_cannot_read_tenant_b(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}iso", "Tenant A", ttl=10, tenant_id="t-a"
        )
        result = await loader.load(
            f"{TEST_PREFIX}iso", tenant_id="t-b", fallback_template="default"
        )
        assert result == "default"

    async def test_global_readable_by_all(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}shared", "Shared", ttl=10
        )
        r_a = await loader.load(f"{TEST_PREFIX}shared", tenant_id="t-a")
        r_b = await loader.load(f"{TEST_PREFIX}shared", tenant_id="t-b")
        assert r_a == "Shared"
        assert r_b == "Shared"
