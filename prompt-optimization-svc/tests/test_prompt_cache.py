"""Tests for PromptCacheManager — Redis DB 2 prompt cache, locks, and progress."""

from unittest.mock import AsyncMock, patch

import pytest

from app.cache.prompt_cache import (
    DEFAULT_PROMPT_TTL,
    LOCK_TTL,
    PROGRESS_TTL,
    PromptCacheManager,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    r = AsyncMock()
    r.get.return_value = None
    r.set.return_value = True
    r.delete.return_value = 1
    r.hset.return_value = True
    r.hgetall.return_value = {}
    r.expire.return_value = True
    r.ttl.return_value = 7200
    r.aclose.return_value = None
    return r


@pytest.fixture
def cache(mock_redis):
    """PromptCacheManager with mocked Redis."""
    mgr = PromptCacheManager(redis_url="redis://localhost:6379/2")
    mgr._redis = mock_redis
    return mgr


# ------------------------------------------------------------------
# Key naming convention (AC-1)
# ------------------------------------------------------------------


class TestKeyPatterns:
    """Verify §9.1 key naming convention."""

    def test_production_key(self):
        key = PromptCacheManager._prompt_key("zorven-wf1-mra-landscape")
        assert key == "prompt:zorven-wf1-mra-landscape:production"

    def test_tenant_key(self):
        key = PromptCacheManager._prompt_key("zorven-wf1-mra-landscape", "tenant-42")
        assert key == "prompt:zorven-wf1-mra-landscape:tenant:tenant-42"

    def test_lock_key(self):
        key = PromptCacheManager._lock_key("wf3-creative-pipeline")
        assert key == "prompt:optimization:lock:wf3-creative-pipeline"

    def test_progress_key(self):
        key = PromptCacheManager._progress_key("run-abc-123")
        assert key == "prompt:optimization:progress:run-abc-123"


# ------------------------------------------------------------------
# Prompt cache (AC-1)
# ------------------------------------------------------------------


class TestPromptCache:
    """Test prompt get/set/invalidate."""

    async def test_set_production_prompt(self, cache, mock_redis):
        await cache.set_prompt("zorven-wf1-mra-landscape", "You are a market researcher")
        mock_redis.set.assert_called_once_with(
            "prompt:zorven-wf1-mra-landscape:production",
            "You are a market researcher",
            ex=DEFAULT_PROMPT_TTL,
        )

    async def test_set_tenant_prompt(self, cache, mock_redis):
        await cache.set_prompt("zorven-wf1-mra-landscape", "Custom prompt", tenant_id="t-99")
        mock_redis.set.assert_called_once_with(
            "prompt:zorven-wf1-mra-landscape:tenant:t-99",
            "Custom prompt",
            ex=DEFAULT_PROMPT_TTL,
        )

    async def test_set_prompt_custom_ttl(self, cache, mock_redis):
        await cache.set_prompt("test", "template", ttl=600)
        mock_redis.set.assert_called_once_with(
            "prompt:test:production", "template", ex=600
        )

    async def test_get_production_prompt_hit(self, cache, mock_redis):
        mock_redis.get.return_value = "cached template"
        result = await cache.get_prompt("test-prompt")
        assert result == "cached template"
        mock_redis.get.assert_called_once_with("prompt:test-prompt:production")

    async def test_get_prompt_miss(self, cache, mock_redis):
        mock_redis.get.return_value = None
        result = await cache.get_prompt("nonexistent")
        assert result is None

    async def test_get_tenant_prompt(self, cache, mock_redis):
        mock_redis.get.return_value = "tenant template"
        result = await cache.get_prompt("test", tenant_id="t-1")
        mock_redis.get.assert_called_once_with("prompt:test:tenant:t-1")
        assert result == "tenant template"

    async def test_invalidate_prompt(self, cache, mock_redis):
        async def fake_scan(*args, **kwargs):
            for key in [
                "prompt:test:production",
                "prompt:test:tenant:t-1",
            ]:
                yield key

        mock_redis.scan_iter = fake_scan
        mock_redis.delete.return_value = 2
        deleted = await cache.invalidate_prompt("test")
        assert deleted == 2

    async def test_invalidate_no_keys(self, cache, mock_redis):
        async def empty_scan(*args, **kwargs):
            return
            yield  # noqa: make it an async generator

        mock_redis.scan_iter = empty_scan
        deleted = await cache.invalidate_prompt("nonexistent")
        assert deleted == 0

    async def test_get_prompt_redis_error_returns_none(self, cache, mock_redis):
        mock_redis.get.side_effect = ConnectionError("refused")
        result = await cache.get_prompt("test")
        assert result is None


# ------------------------------------------------------------------
# Optimization lock (AC-2)
# ------------------------------------------------------------------


class TestOptimizationLock:
    """Test distributed optimization lock."""

    async def test_acquire_lock_success(self, cache, mock_redis):
        mock_redis.set.return_value = True
        acquired = await cache.acquire_optimization_lock("wf3-creative", "worker-1")
        assert acquired is True
        mock_redis.set.assert_called_once_with(
            "prompt:optimization:lock:wf3-creative",
            "worker-1",
            nx=True,
            ex=LOCK_TTL,
        )

    async def test_acquire_lock_already_held(self, cache, mock_redis):
        mock_redis.set.return_value = None  # NX failed
        acquired = await cache.acquire_optimization_lock("wf3-creative", "worker-2")
        assert acquired is False

    async def test_acquire_lock_custom_ttl(self, cache, mock_redis):
        mock_redis.set.return_value = True
        await cache.acquire_optimization_lock("grp", "owner", ttl=3600)
        mock_redis.set.assert_called_once_with(
            "prompt:optimization:lock:grp", "owner", nx=True, ex=3600
        )

    async def test_release_lock_by_owner(self, cache, mock_redis):
        mock_redis.get.return_value = "worker-1"
        released = await cache.release_optimization_lock("wf3-creative", "worker-1")
        assert released is True
        mock_redis.delete.assert_called_once_with(
            "prompt:optimization:lock:wf3-creative"
        )

    async def test_release_lock_wrong_owner(self, cache, mock_redis):
        mock_redis.get.return_value = "worker-1"
        released = await cache.release_optimization_lock("wf3-creative", "worker-2")
        assert released is False
        mock_redis.delete.assert_not_called()

    async def test_release_lock_not_held(self, cache, mock_redis):
        mock_redis.get.return_value = None
        released = await cache.release_optimization_lock("grp", "owner")
        assert released is False

    async def test_get_lock_info(self, cache, mock_redis):
        mock_redis.get.return_value = "worker-1"
        mock_redis.ttl.return_value = 5400
        info = await cache.get_optimization_lock_info("wf3-creative")
        assert info == {
            "group": "wf3-creative",
            "owner": "worker-1",
            "ttl_seconds": 5400,
        }

    async def test_get_lock_info_not_held(self, cache, mock_redis):
        mock_redis.get.return_value = None
        info = await cache.get_optimization_lock_info("grp")
        assert info is None

    async def test_lock_ttl_is_2_hours(self):
        assert LOCK_TTL == 7200


# ------------------------------------------------------------------
# Optimization progress (AC-3)
# ------------------------------------------------------------------


class TestOptimizationProgress:
    """Test optimization progress hash."""

    async def test_set_progress(self, cache, mock_redis):
        progress = {"state": "OPTIMIZING", "percent": 45}
        await cache.set_optimization_progress("run-123", progress)
        mock_redis.hset.assert_called_once()
        # Verify the key was passed (positional or keyword)
        call_args = mock_redis.hset.call_args
        key_arg = call_args[0][0] if call_args[0] else call_args[1].get("name", call_args[1].get("key"))
        assert key_arg == "prompt:optimization:progress:run-123"
        mock_redis.expire.assert_called_once_with(
            "prompt:optimization:progress:run-123", PROGRESS_TTL
        )

    async def test_set_progress_ttl_is_24_hours(self):
        assert PROGRESS_TTL == 86400

    async def test_get_progress(self, cache, mock_redis):
        mock_redis.hgetall.return_value = {
            "state": "OPTIMIZING",
            "percent": "45",
            "updated_at": "2026-05-22T10:00:00+00:00",
        }
        result = await cache.get_optimization_progress("run-123")
        assert result["state"] == "OPTIMIZING"
        assert result["percent"] == "45"

    async def test_get_progress_not_found(self, cache, mock_redis):
        mock_redis.hgetall.return_value = {}
        result = await cache.get_optimization_progress("nonexistent")
        assert result is None

    async def test_delete_progress(self, cache, mock_redis):
        await cache.delete_optimization_progress("run-123")
        mock_redis.delete.assert_called_once_with(
            "prompt:optimization:progress:run-123"
        )

    async def test_progress_redis_error_returns_none(self, cache, mock_redis):
        mock_redis.hgetall.side_effect = ConnectionError("refused")
        result = await cache.get_optimization_progress("run-123")
        assert result is None
