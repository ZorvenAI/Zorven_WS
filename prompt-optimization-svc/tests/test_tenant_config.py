"""Tests for tenant-configurable cache TTL using real Redis (US-011)."""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import (
    DEFAULT_TTL,
    MAX_TTL,
    MIN_TTL,
    TenantConfigManager,
    clamp_ttl,
)
from .conftest import REDIS_URL, requires_redis


class TestClampTTL:
    def test_below_min(self):
        assert clamp_ttl(5) == MIN_TTL

    def test_zero(self):
        assert clamp_ttl(0) == MIN_TTL

    def test_negative(self):
        assert clamp_ttl(-100) == MIN_TTL

    def test_above_max(self):
        assert clamp_ttl(5000) == MAX_TTL

    def test_exactly_min(self):
        assert clamp_ttl(10) == 10

    def test_exactly_max(self):
        assert clamp_ttl(3600) == 3600

    def test_within_range(self):
        assert clamp_ttl(600) == 600

    def test_constants(self):
        assert MIN_TTL == 10
        assert MAX_TTL == 3600
        assert DEFAULT_TTL == 300


@requires_redis
class TestGetTTL:
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

    async def test_missing_config_returns_default(self, config):
        ttl = await config.get_prompt_cache_ttl("__test-missing-xyz")
        assert ttl == DEFAULT_TTL

    async def test_none_tenant_returns_default(self, config):
        assert await config.get_prompt_cache_ttl(None) == DEFAULT_TTL

    async def test_stored_value_returned(self, config):
        await config.set_prompt_cache_ttl("__test-stored", 600)
        assert await config.get_prompt_cache_ttl("__test-stored") == 600

    async def test_stored_value_clamped_below(self, config):
        await config.set_prompt_cache_ttl("__test-below", 5)
        assert await config.get_prompt_cache_ttl("__test-below") == MIN_TTL

    async def test_correct_redis_key(self, config):
        await config.set_prompt_cache_ttl("__test-key", 600)
        r = await config.prompt_cache.connect()
        val = await r.get("tenant:__test-key:config.prompt_cache_ttl_seconds")
        assert val == "600"


@requires_redis
class TestSetTTL:
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

    async def test_set_within_range(self, config):
        await config.set_prompt_cache_ttl("__test-set", 600)
        assert await config.get_prompt_cache_ttl("__test-set") == 600

    async def test_set_below_min_clamped(self, config):
        await config.set_prompt_cache_ttl("__test-min", 5)
        assert await config.get_prompt_cache_ttl("__test-min") == 10

    async def test_set_above_max_clamped(self, config):
        await config.set_prompt_cache_ttl("__test-max", 5000)
        assert await config.get_prompt_cache_ttl("__test-max") == 3600


@requires_redis
class TestSetThenGet:
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

    async def test_update_takes_effect(self, config):
        await config.set_prompt_cache_ttl("__test-upd", 300)
        assert await config.get_prompt_cache_ttl("__test-upd") == 300
        await config.set_prompt_cache_ttl("__test-upd", 60)
        assert await config.get_prompt_cache_ttl("__test-upd") == 60
