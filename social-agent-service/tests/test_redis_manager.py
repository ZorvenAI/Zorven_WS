"""Tests for Redis manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.cache.redis_manager import RedisManager


class TestPostLock:
    async def test_post_lock_acquire_release(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            acquired = await manager.acquire_post_lock("tenant-1", "linkedin")
            assert acquired is True
            mock_redis.set.assert_called_once()

            await manager.release_post_lock("tenant-1", "linkedin")
            mock_redis.delete.assert_called_once()

    async def test_post_lock_not_acquired(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=None)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            acquired = await manager.acquire_post_lock("tenant-1", "linkedin")
            assert acquired is False


class TestDraftStorage:
    async def test_draft_store_and_retrieve(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()

        import json

        draft_data = {"platform": "linkedin", "content": "Test post"}
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(draft_data))

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            await manager.store_draft("job-1", "linkedin", draft_data)
            mock_redis.set.assert_called_once()

            result = await manager.get_draft("job-1", "linkedin")
            assert result == draft_data

    async def test_draft_not_found(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            result = await manager.get_draft("job-1", "linkedin")
            assert result is None


class TestRateLimit:
    async def test_rate_limit_within(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            within = await manager.check_rate_limit("tenant-1", limit=10)
            assert within is True

    async def test_rate_limit_exceeded(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=11)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            within = await manager.check_rate_limit("tenant-1", limit=10)
            assert within is False

    async def test_redis_error_returns_true(self):
        """Fail-open: Redis errors should not block requests."""
        manager = RedisManager("redis://localhost:6379/6")

        async def raise_error():
            raise ConnectionError("Redis down")

        with patch.object(manager, "_get_redis", side_effect=raise_error):
            within = await manager.check_rate_limit("tenant-1", limit=10)
            assert within is True


class TestResultCache:
    async def test_cache_set_and_get(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()

        import json

        cached_data = {"findings": ["test"]}
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data))

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            await manager.set_cached_result("test-key", cached_data)
            result = await manager.get_cached_result("test-key")
            assert result == cached_data

    async def test_cache_miss(self):
        manager = RedisManager("redis://localhost:6379/6")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch.object(manager, "_get_redis", return_value=mock_redis):
            result = await manager.get_cached_result("missing-key")
            assert result is None
