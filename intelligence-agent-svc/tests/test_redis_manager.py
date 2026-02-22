"""Tests for RedisManager caching and rate limiting.

These tests mock the Redis client to avoid requiring a live Redis instance.
Integration tests with real Redis are in tests/integration/.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.cache.redis_manager import RedisManager


class TestBenchmarkCache:
    """Verify benchmark get/set operations."""

    async def test_get_benchmarks_cache_hit(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"technology": 0.04}'
        manager._redis = mock_redis

        result = await manager.get_benchmarks("technology")
        assert result == {"technology": 0.04}
        mock_redis.get.assert_called_once_with("intel:benchmarks:technology")

    async def test_get_benchmarks_cache_miss(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        manager._redis = mock_redis

        result = await manager.get_benchmarks("technology")
        assert result is None

    async def test_set_benchmarks(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.set_benchmarks("technology", {"rate": 0.04})
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert "intel:benchmarks:technology" in call_args.args

    async def test_get_benchmarks_redis_error_returns_none(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Connection refused")
        manager._redis = mock_redis

        result = await manager.get_benchmarks("technology")
        assert result is None


class TestWACCCache:
    """Verify WACC get/set operations."""

    async def test_get_wacc_cache_hit(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "0.10"
        manager._redis = mock_redis

        result = await manager.get_wacc("us")
        assert result == 0.10

    async def test_get_wacc_cache_miss(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        manager._redis = mock_redis

        result = await manager.get_wacc("us")
        assert result is None


class TestResultCache:
    """Verify result cache operations."""

    async def test_get_cached_result_hit(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = '{"findings": ["cached"]}'
        manager._redis = mock_redis

        result = await manager.get_cached_result("test-key")
        assert result == {"findings": ["cached"]}

    async def test_get_cached_result_miss(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        manager._redis = mock_redis

        result = await manager.get_cached_result("test-key")
        assert result is None

    async def test_set_cached_result(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.set_cached_result("test-key", {"findings": ["a"]})
        mock_redis.set.assert_called_once()


class TestRateLimiting:
    """Verify rate limiting logic."""

    async def test_within_limit_returns_true(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is True
        mock_redis.expire.assert_called_once()

    async def test_at_limit_returns_true(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 10
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is True

    async def test_over_limit_returns_false(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 11
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is False

    async def test_redis_error_fails_open(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.incr.side_effect = Exception("Connection refused")
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is True  # Fail open

    async def test_expire_set_on_first_increment(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        manager._redis = mock_redis

        await manager.check_rate_limit("tenant-1", limit=10)
        mock_redis.expire.assert_called_once_with("intel:rate:tenant-1", 60)

    async def test_no_expire_on_subsequent_increments(self):
        manager = RedisManager("redis://localhost:6379/3")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 5  # Not the first request
        manager._redis = mock_redis

        await manager.check_rate_limit("tenant-1", limit=10)
        mock_redis.expire.assert_not_called()


class TestHashKey:
    """Verify key hashing."""

    def test_hash_is_deterministic(self):
        h1 = RedisManager._hash("test-value")
        h2 = RedisManager._hash("test-value")
        assert h1 == h2

    def test_different_values_different_hashes(self):
        h1 = RedisManager._hash("value-a")
        h2 = RedisManager._hash("value-b")
        assert h1 != h2
