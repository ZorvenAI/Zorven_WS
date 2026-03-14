"""Tests for Redis manager — caching, rate limiting, idempotency, and alerts."""

from unittest.mock import AsyncMock

from app.cache.redis_manager import RedisManager


class TestCacheGetSet:
    """Round-trip cache get/set tests."""

    def setup_method(self) -> None:
        self.manager = RedisManager("redis://localhost:6379/14")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_get_cached_result_hit(self) -> None:
        self.mock_redis.get.return_value = '{"scored_trends": []}'
        result = await self.manager.get_cached_result(
            "analyze trends", {}, "t1"
        )
        assert result == {"scored_trends": []}

    async def test_get_cached_result_miss(self) -> None:
        self.mock_redis.get.return_value = None
        result = await self.manager.get_cached_result(
            "analyze trends", {}, "t1"
        )
        assert result is None

    async def test_set_cached_result(self) -> None:
        await self.manager.cache_result(
            "analyze trends", {}, {"scored_trends": []}, "t1"
        )
        self.mock_redis.setex.assert_awaited_once()

    async def test_get_cached_result_error_returns_none(self) -> None:
        self.mock_redis.get.side_effect = Exception("Redis down")
        result = await self.manager.get_cached_result(
            "analyze trends", {}, "t1"
        )
        assert result is None

    async def test_set_cached_result_error_silent(self) -> None:
        self.mock_redis.setex.side_effect = Exception("Redis down")
        # Should not raise
        await self.manager.cache_result(
            "analyze trends", {}, {"data": "test"}, "t1"
        )

    async def test_cache_key_deterministic(self) -> None:
        key1 = self.manager._cache_key("test", {"a": 1}, "t1")
        key2 = self.manager._cache_key("test", {"a": 1}, "t1")
        assert key1 == key2

    async def test_cache_key_varies_by_prompt(self) -> None:
        key1 = self.manager._cache_key("test1", {}, "t1")
        key2 = self.manager._cache_key("test2", {}, "t1")
        assert key1 != key2

    async def test_cache_key_varies_by_config(self) -> None:
        key1 = self.manager._cache_key("test", {"a": 1}, "t1")
        key2 = self.manager._cache_key("test", {"b": 2}, "t1")
        assert key1 != key2

    async def test_cache_key_varies_by_tenant(self) -> None:
        key1 = self.manager._cache_key("test", {}, "t1")
        key2 = self.manager._cache_key("test", {}, "t2")
        assert key1 != key2


class TestStubMode:
    """Tests when Redis is not connected (stub mode)."""

    def setup_method(self) -> None:
        self.manager = RedisManager("")

    async def test_get_cached_result_returns_none(self) -> None:
        result = await self.manager.get_cached_result("test", {}, "t1")
        assert result is None

    async def test_cache_result_noop(self) -> None:
        # Should not raise
        await self.manager.cache_result("test", {}, {"data": "test"}, "t1")

    async def test_rate_limit_allows(self) -> None:
        result = await self.manager.check_rate_limit("t1")
        assert result is True

    async def test_idempotency_returns_false(self) -> None:
        result = await self.manager.check_idempotency("key-1")
        assert result is False

    async def test_alert_count_returns_zero(self) -> None:
        count = await self.manager.get_alert_count("t1")
        assert count == 0

    async def test_increment_alert_returns_zero(self) -> None:
        count = await self.manager.increment_alert_count("t1")
        assert count == 0


class TestRateLimit:
    """Rate limiting via INCR + EXPIRE."""

    def setup_method(self) -> None:
        self.manager = RedisManager("redis://localhost:6379/14")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_first_request_allowed_and_sets_expire(self) -> None:
        self.mock_redis.incr.return_value = 1
        result = await self.manager.check_rate_limit("t1")
        assert result is True
        self.mock_redis.expire.assert_awaited_once()

    async def test_within_limit_allowed(self) -> None:
        self.mock_redis.incr.return_value = 5
        result = await self.manager.check_rate_limit("t1", limit=10)
        assert result is True

    async def test_at_limit_allowed(self) -> None:
        self.mock_redis.incr.return_value = 10
        result = await self.manager.check_rate_limit("t1", limit=10)
        assert result is True

    async def test_over_limit_rejected(self) -> None:
        self.mock_redis.incr.return_value = 11
        result = await self.manager.check_rate_limit("t1", limit=10)
        assert result is False

    async def test_redis_error_allows_request(self) -> None:
        self.mock_redis.incr.side_effect = Exception("Redis down")
        result = await self.manager.check_rate_limit("t1")
        assert result is True  # Fail open


class TestIdempotency:
    """Idempotency set and check."""

    def setup_method(self) -> None:
        self.manager = RedisManager("redis://localhost:6379/14")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_not_processed_returns_false(self) -> None:
        self.mock_redis.exists.return_value = 0
        result = await self.manager.check_idempotency("key-1")
        assert result is False

    async def test_already_processed_returns_true(self) -> None:
        self.mock_redis.exists.return_value = 1
        result = await self.manager.check_idempotency("key-1")
        assert result is True

    async def test_set_idempotency(self) -> None:
        await self.manager.set_idempotency("key-1", ttl=3600)
        self.mock_redis.setex.assert_awaited_once()
        call_args = self.mock_redis.setex.call_args
        assert "tcia:idempotency:key-1" in call_args[0]
        assert call_args[0][1] == 3600

    async def test_redis_error_returns_false(self) -> None:
        self.mock_redis.exists.side_effect = Exception("Redis down")
        result = await self.manager.check_idempotency("key-1")
        assert result is False


class TestAlertCounter:
    """Alert count increment and get."""

    def setup_method(self) -> None:
        self.manager = RedisManager("redis://localhost:6379/14")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_get_alert_count_zero(self) -> None:
        self.mock_redis.get.return_value = None
        count = await self.manager.get_alert_count("t1")
        assert count == 0

    async def test_get_alert_count_existing(self) -> None:
        self.mock_redis.get.return_value = "3"
        count = await self.manager.get_alert_count("t1")
        assert count == 3

    async def test_increment_first_sets_expire(self) -> None:
        self.mock_redis.incr.return_value = 1
        count = await self.manager.increment_alert_count("t1")
        assert count == 1
        self.mock_redis.expire.assert_awaited_once()

    async def test_increment_subsequent_no_expire(self) -> None:
        self.mock_redis.incr.return_value = 3
        count = await self.manager.increment_alert_count("t1")
        assert count == 3
        self.mock_redis.expire.assert_not_awaited()

    async def test_get_error_returns_zero(self) -> None:
        self.mock_redis.get.side_effect = Exception("Redis down")
        count = await self.manager.get_alert_count("t1")
        assert count == 0

    async def test_increment_error_returns_zero(self) -> None:
        self.mock_redis.incr.side_effect = Exception("Redis down")
        count = await self.manager.increment_alert_count("t1")
        assert count == 0


class TestConnection:
    """Connection and close lifecycle."""

    async def test_close_when_not_connected(self) -> None:
        manager = RedisManager("redis://localhost:6379/14")
        await manager.close()
        assert manager._redis is None

    async def test_close_when_connected(self) -> None:
        manager = RedisManager("redis://localhost:6379/14")
        mock_redis = AsyncMock()
        manager._redis = mock_redis
        await manager.close()
        mock_redis.aclose.assert_awaited_once()
        assert manager._redis is None


class TestRegistryHelpers:
    """Hash and Sorted Set helpers used by TrendRegistry."""

    def setup_method(self) -> None:
        self.manager = RedisManager("redis://localhost:6379/14")
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_hset(self) -> None:
        await self.manager.hset("key", "field", "value")
        self.mock_redis.hset.assert_awaited_once_with("key", "field", "value")

    async def test_hget(self) -> None:
        self.mock_redis.hget.return_value = "value"
        result = await self.manager.hget("key", "field")
        assert result == "value"

    async def test_hgetall(self) -> None:
        self.mock_redis.hgetall.return_value = {"f1": "v1", "f2": "v2"}
        result = await self.manager.hgetall("key")
        assert result == {"f1": "v1", "f2": "v2"}

    async def test_hdel(self) -> None:
        self.mock_redis.hdel.return_value = 1
        result = await self.manager.hdel("key", "field")
        assert result == 1

    async def test_hlen(self) -> None:
        self.mock_redis.hlen.return_value = 5
        result = await self.manager.hlen("key")
        assert result == 5

    async def test_zadd(self) -> None:
        self.mock_redis.zadd.return_value = 1
        result = await self.manager.zadd("key", {"member": 1.0})
        assert result == 1

    async def test_zrangebyscore(self) -> None:
        self.mock_redis.zrangebyscore.return_value = [("m1", 1.0)]
        result = await self.manager.zrangebyscore(
            "key", 0, "+inf", withscores=True
        )
        assert result == [("m1", 1.0)]

    async def test_zremrangebyscore(self) -> None:
        self.mock_redis.zremrangebyscore.return_value = 2
        result = await self.manager.zremrangebyscore("key", "-inf", 100.0)
        assert result == 2

    async def test_expire(self) -> None:
        await self.manager.expire("key", 3600)
        self.mock_redis.expire.assert_awaited_once_with("key", 3600)

    async def test_stub_mode_hset_noop(self) -> None:
        manager = RedisManager("")
        await manager.hset("key", "field", "value")
        # No assertion needed; just verify no exception

    async def test_stub_mode_hget_returns_none(self) -> None:
        manager = RedisManager("")
        result = await manager.hget("key", "field")
        assert result is None

    async def test_stub_mode_hgetall_returns_empty(self) -> None:
        manager = RedisManager("")
        result = await manager.hgetall("key")
        assert result == {}

    async def test_stub_mode_zadd_returns_zero(self) -> None:
        manager = RedisManager("")
        result = await manager.zadd("key", {"m": 1.0})
        assert result == 0
