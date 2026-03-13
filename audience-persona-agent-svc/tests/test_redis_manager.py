"""Tests for the Redis manager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cache.redis_manager import RedisManager


class TestRedisManager:
    def setup_method(self):
        self.manager = RedisManager()
        self.mock_redis = AsyncMock()
        self.manager._redis = self.mock_redis

    async def test_cache_key_deterministic(self):
        """Same input produces same cache key."""
        key1 = RedisManager._cache_key("test prompt", {"key": "value"})
        key2 = RedisManager._cache_key("test prompt", {"key": "value"})
        assert key1 == key2
        assert key1.startswith("apa:result:")

    async def test_cache_key_differs_for_different_input(self):
        """Different inputs produce different cache keys."""
        key1 = RedisManager._cache_key("prompt A", {})
        key2 = RedisManager._cache_key("prompt B", {})
        assert key1 != key2

    async def test_get_cached_result_hit(self):
        """Returns cached data on hit."""
        import json

        expected = {"query": "test", "personas": []}
        self.mock_redis.get.return_value = json.dumps(expected)

        result = await self.manager.get_cached_result("test", {})
        assert result == expected

    async def test_get_cached_result_miss(self):
        """Returns None on cache miss."""
        self.mock_redis.get.return_value = None
        result = await self.manager.get_cached_result("test", {})
        assert result is None

    async def test_get_cached_result_no_redis(self):
        """Returns None when Redis is not connected."""
        self.manager._redis = None
        result = await self.manager.get_cached_result("test", {})
        assert result is None

    async def test_cache_result(self):
        """Caches result with TTL."""
        await self.manager.cache_result("test", {}, {"data": "value"})
        self.mock_redis.setex.assert_called_once()

    async def test_rate_limit_allows(self):
        """Rate limit allows requests under threshold."""
        self.mock_redis.incr.return_value = 1
        allowed = await self.manager.check_rate_limit("tenant-1")
        assert allowed is True

    async def test_rate_limit_blocks(self):
        """Rate limit blocks requests over threshold."""
        self.mock_redis.incr.return_value = 11
        allowed = await self.manager.check_rate_limit("tenant-1")
        assert allowed is False

    async def test_rate_limit_fail_open(self):
        """Rate limit allows on Redis error."""
        self.manager._redis = None
        allowed = await self.manager.check_rate_limit("tenant-1")
        assert allowed is True

    async def test_idempotency_new(self):
        """Idempotency check returns True for new operations."""
        self.mock_redis.set.return_value = True
        is_new = await self.manager.check_idempotency("op-123")
        assert is_new is True

    async def test_idempotency_duplicate(self):
        """Idempotency check returns False for duplicate operations."""
        self.mock_redis.set.return_value = None
        is_new = await self.manager.check_idempotency("op-123")
        assert is_new is False

    async def test_odoo_survey_cache(self):
        """Odoo survey cache set and get."""
        import json

        data = {"survey_count": 5}
        await self.manager.set_odoo_survey_cache("t1", "s1", data)
        self.mock_redis.setex.assert_called_once()

        self.mock_redis.get.return_value = json.dumps(data)
        result = await self.manager.get_odoo_survey_cache("t1", "s1")
        assert result == data

    async def test_odoo_crm_cache(self):
        """Odoo CRM cache set and get."""
        import json

        data = {"customer_count": 50}
        await self.manager.set_odoo_crm_cache("t1", data)
        self.mock_redis.setex.assert_called_once()

        self.mock_redis.get.return_value = json.dumps(data)
        result = await self.manager.get_odoo_crm_cache("t1")
        assert result == data
