"""Tests for Redis manager — caching and rate limiting."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.redis_manager import RedisManager


class TestRedisManager:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/11")

    async def test_close_when_not_connected(self):
        """Close is no-op when no connection exists."""
        await self.manager.close()
        assert self.manager._redis is None

    async def test_close_when_connected(self):
        mock_redis = AsyncMock()
        self.manager._redis = mock_redis
        await self.manager.close()
        mock_redis.aclose.assert_awaited_once()
        assert self.manager._redis is None


class TestResultCache:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/11")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_get_cached_result_hit(self):
        self.mock_redis.get.return_value = '{"query": "test"}'
        result = await self.manager.get_cached_result("abc123")
        assert result == {"query": "test"}

    async def test_get_cached_result_miss(self):
        self.mock_redis.get.return_value = None
        result = await self.manager.get_cached_result("abc123")
        assert result is None

    async def test_get_cached_result_error_returns_none(self):
        self.mock_redis.get.side_effect = Exception("Redis down")
        result = await self.manager.get_cached_result("abc123")
        assert result is None

    async def test_set_cached_result(self):
        await self.manager.set_cached_result("abc123", {"query": "test"}, ttl=3600)
        self.mock_redis.set.assert_awaited_once()
        call_args = self.mock_redis.set.call_args
        assert "mra:result:abc123" in call_args.args
        assert call_args.kwargs.get("ex") == 3600

    async def test_set_cached_result_error_silent(self):
        self.mock_redis.set.side_effect = Exception("Redis down")
        # Should not raise
        await self.manager.set_cached_result("abc123", {"query": "test"})


class TestEconomicCache:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/11")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_get_cached_economic_hit(self):
        self.mock_redis.get.return_value = '{"data": [{"value": 100}]}'
        result = await self.manager.get_cached_economic("GDP", "WLD", "2020:2024")
        assert result == {"data": [{"value": 100}]}

    async def test_get_cached_economic_miss(self):
        self.mock_redis.get.return_value = None
        result = await self.manager.get_cached_economic("GDP", "WLD", "2020:2024")
        assert result is None

    async def test_set_cached_economic(self):
        await self.manager.set_cached_economic(
            "GDP", "WLD", "2020:2024", {"data": [{"value": 100}]}
        )
        self.mock_redis.set.assert_awaited_once()


class TestNewsCache:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/11")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_get_cached_news_hit(self):
        self.mock_redis.get.return_value = '[{"title": "Test"}]'
        result = await self.manager.get_cached_news("AI market")
        assert result == [{"title": "Test"}]

    async def test_get_cached_news_miss(self):
        self.mock_redis.get.return_value = None
        result = await self.manager.get_cached_news("AI market")
        assert result is None

    async def test_set_cached_news(self):
        await self.manager.set_cached_news("AI market", [{"title": "Test"}])
        self.mock_redis.set.assert_awaited_once()


class TestRateLimiting:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/11")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_first_request_allowed(self):
        self.mock_redis.incr.return_value = 1
        result = await self.manager.check_rate_limit("tenant-1")
        assert result is True
        self.mock_redis.expire.assert_awaited_once()

    async def test_within_limit_allowed(self):
        self.mock_redis.incr.return_value = 5
        result = await self.manager.check_rate_limit("tenant-1", limit=10)
        assert result is True

    async def test_at_limit_allowed(self):
        self.mock_redis.incr.return_value = 10
        result = await self.manager.check_rate_limit("tenant-1", limit=10)
        assert result is True

    async def test_over_limit_rejected(self):
        self.mock_redis.incr.return_value = 11
        result = await self.manager.check_rate_limit("tenant-1", limit=10)
        assert result is False

    async def test_redis_error_allows_request(self):
        self.mock_redis.incr.side_effect = Exception("Redis down")
        result = await self.manager.check_rate_limit("tenant-1")
        assert result is True  # Fail open
