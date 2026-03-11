"""Integration tests for Redis caching — requires running Redis."""

import pytest

from app.cache.redis_manager import RedisManager

pytestmark = pytest.mark.integration


class TestResultCacheIntegration:
    async def test_set_and_get_result(self, redis_manager: RedisManager):
        await redis_manager.set_cached_result("test-key", {"query": "test"}, ttl=60)
        result = await redis_manager.get_cached_result("test-key")
        assert result == {"query": "test"}

    async def test_cache_miss(self, redis_manager: RedisManager):
        result = await redis_manager.get_cached_result("nonexistent-key")
        assert result is None


class TestEconomicCacheIntegration:
    async def test_set_and_get_economic(self, redis_manager: RedisManager):
        await redis_manager.set_cached_economic(
            "GDP", "WLD", "2020:2024", {"data": [{"value": 100}]}
        )
        result = await redis_manager.get_cached_economic("GDP", "WLD", "2020:2024")
        assert result == {"data": [{"value": 100}]}


class TestNewsCacheIntegration:
    async def test_set_and_get_news(self, redis_manager: RedisManager):
        await redis_manager.set_cached_news("AI market", [{"title": "Test"}])
        result = await redis_manager.get_cached_news("AI market")
        assert result == [{"title": "Test"}]
