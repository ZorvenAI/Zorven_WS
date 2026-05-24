"""Tests for PromptCacheManager using real Redis (US-004)."""

import pytest

from app.cache.prompt_cache import (
    DEFAULT_PROMPT_TTL,
    LOCK_TTL,
    PROGRESS_TTL,
    PromptCacheManager,
)

from .conftest import REDIS_URL, requires_redis


class TestKeyPatterns:
    """Verify §9.1 key naming convention."""

    def test_production_key(self):
        key = PromptCacheManager._prompt_key("zorven-wf1-mra-landscape")
        assert key == "prompt:zorven-wf1-mra-landscape:production"

    def test_tenant_key(self):
        key = PromptCacheManager._prompt_key(
            "zorven-wf1-mra-landscape", "tenant-42"
        )
        assert key == "prompt:zorven-wf1-mra-landscape:tenant:tenant-42"

    def test_lock_key(self):
        key = PromptCacheManager._lock_key("wf3-creative-pipeline")
        assert key == "prompt:optimization:lock:wf3-creative-pipeline"

    def test_progress_key(self):
        key = PromptCacheManager._progress_key("run-abc-123")
        assert key == "prompt:optimization:progress:run-abc-123"


@requires_redis
class TestPromptCache:
    """Test prompt get/set/invalidate with real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        r = await mgr.connect()
        async for key in r.scan_iter(match="prompt:__test*"):
            await r.delete(key)
        await mgr.close()

    async def test_set_and_get_production_prompt(self, cache):
        await cache.set_prompt("__test-set", "Template text", ttl=10)
        result = await cache.get_prompt("__test-set")
        assert result == "Template text"

    async def test_set_and_get_tenant_prompt(self, cache):
        await cache.set_prompt(
            "__test-tenant", "Tenant template", ttl=10, tenant_id="t-99"
        )
        result = await cache.get_prompt("__test-tenant", tenant_id="t-99")
        assert result == "Tenant template"

    async def test_set_prompt_custom_ttl(self, cache):
        await cache.set_prompt("__test-ttl", "template", ttl=5)
        result = await cache.get_prompt("__test-ttl")
        assert result == "template"

    async def test_get_prompt_miss(self, cache):
        result = await cache.get_prompt("__test-nonexistent")
        assert result is None

    async def test_invalidate_prompt(self, cache):
        await cache.set_prompt("__test-inv", "prod", ttl=10)
        await cache.set_prompt(
            "__test-inv", "tenant", ttl=10, tenant_id="t-1"
        )
        deleted = await cache.invalidate_prompt("__test-inv")
        assert deleted >= 2

    async def test_invalidate_no_keys(self, cache):
        deleted = await cache.invalidate_prompt("__test-no-keys-xyz")
        assert deleted == 0


@requires_redis
class TestOptimizationLock:
    """Test distributed optimization lock with real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        r = await mgr.connect()
        async for key in r.scan_iter(
            match="prompt:optimization:lock:__test*"
        ):
            await r.delete(key)
        await mgr.close()

    async def test_acquire_lock_success(self, cache):
        acquired = await cache.acquire_optimization_lock(
            "__test-lock", "worker-1", ttl=30
        )
        assert acquired is True

    async def test_acquire_lock_already_held(self, cache):
        await cache.acquire_optimization_lock(
            "__test-held", "worker-1", ttl=30
        )
        acquired = await cache.acquire_optimization_lock(
            "__test-held", "worker-2", ttl=30
        )
        assert acquired is False

    async def test_release_lock_by_owner(self, cache):
        await cache.acquire_optimization_lock(
            "__test-rel", "worker-1", ttl=30
        )
        released = await cache.release_optimization_lock(
            "__test-rel", "worker-1"
        )
        assert released is True

    async def test_release_lock_wrong_owner(self, cache):
        await cache.acquire_optimization_lock(
            "__test-wrong", "worker-1", ttl=30
        )
        released = await cache.release_optimization_lock(
            "__test-wrong", "worker-2"
        )
        assert released is False

    async def test_get_lock_info(self, cache):
        await cache.acquire_optimization_lock(
            "__test-info", "worker-1", ttl=30
        )
        info = await cache.get_optimization_lock_info("__test-info")
        assert info is not None
        assert info["owner"] == "worker-1"

    async def test_get_lock_info_not_held(self, cache):
        info = await cache.get_optimization_lock_info("__test-nope-xyz")
        assert info is None

    def test_lock_ttl_is_2_hours(self):
        assert LOCK_TTL == 7200


@requires_redis
class TestOptimizationProgress:
    """Test optimization progress hash with real Redis."""

    @pytest.fixture
    async def cache(self):
        mgr = PromptCacheManager(redis_url=REDIS_URL)
        await mgr.connect()
        yield mgr
        r = await mgr.connect()
        async for key in r.scan_iter(
            match="prompt:optimization:progress:__test*"
        ):
            await r.delete(key)
        await mgr.close()

    async def test_set_and_get_progress(self, cache):
        progress = {"state": "OPTIMIZING", "percent": "45"}
        await cache.set_optimization_progress("__test-prog", progress)
        result = await cache.get_optimization_progress("__test-prog")
        assert result is not None
        assert result["state"] == "OPTIMIZING"

    def test_progress_ttl_is_24_hours(self):
        assert PROGRESS_TTL == 86400

    async def test_get_progress_not_found(self, cache):
        result = await cache.get_optimization_progress("__test-nope-xyz")
        assert result is None

    async def test_delete_progress(self, cache):
        await cache.set_optimization_progress(
            "__test-del", {"state": "DONE"}
        )
        await cache.delete_optimization_progress("__test-del")
        result = await cache.get_optimization_progress("__test-del")
        assert result is None
