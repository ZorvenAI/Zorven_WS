"""Tests for Redis manager — caching, rate limiting, and idempotency."""

from unittest.mock import AsyncMock

from app.cache.redis_manager import RedisManager


class TestRedisManager:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/12")

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
        self.manager = RedisManager("redis://localhost:6379/12")
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
        assert "cia:result:abc123" in call_args.args
        assert call_args.kwargs.get("ex") == 3600

    async def test_set_cached_result_error_silent(self):
        self.mock_redis.set.side_effect = Exception("Redis down")
        # Should not raise
        await self.manager.set_cached_result("abc123", {"query": "test"})


class TestProfileCache:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/12")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_get_cached_profile_hit(self):
        self.mock_redis.get.return_value = '{"name": "Acme Corp"}'
        result = await self.manager.get_cached_profile("tenant-1", "acme-corp")
        assert result == {"name": "Acme Corp"}

    async def test_get_cached_profile_miss(self):
        self.mock_redis.get.return_value = None
        result = await self.manager.get_cached_profile("tenant-1", "acme-corp")
        assert result is None

    async def test_set_cached_profile(self):
        await self.manager.set_cached_profile("tenant-1", "acme-corp", {"name": "Acme"})
        self.mock_redis.set.assert_awaited_once()
        call_args = self.mock_redis.set.call_args
        assert "cia:profile:tenant-1:acme-corp" in call_args.args


class TestRateLimiting:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/12")
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


class TestIdempotency:
    def setup_method(self):
        self.manager = RedisManager("redis://localhost:6379/12")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_check_idempotency_not_processed(self):
        self.mock_redis.exists.return_value = 0
        result = await self.manager.check_idempotency("key-1")
        assert result is False

    async def test_check_idempotency_already_processed(self):
        self.mock_redis.exists.return_value = 1
        result = await self.manager.check_idempotency("key-1")
        assert result is True

    async def test_set_idempotency(self):
        await self.manager.set_idempotency("key-1", ttl=3600)
        self.mock_redis.set.assert_awaited_once()
        call_args = self.mock_redis.set.call_args
        assert "cia:idempotent:key-1" in call_args.args
        assert call_args.kwargs.get("ex") == 3600

    async def test_check_idempotency_redis_error_returns_false(self):
        self.mock_redis.exists.side_effect = Exception("Redis down")
        result = await self.manager.check_idempotency("key-1")
        assert result is False
