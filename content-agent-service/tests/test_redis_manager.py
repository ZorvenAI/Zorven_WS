"""Tests for RedisManager — caching and rate limiting."""

from unittest.mock import AsyncMock, patch

from app.cache.redis_manager import RedisManager


class TestSEOKeywords:
    """SEO keyword cache tests."""

    async def test_seo_keyword_roundtrip(self) -> None:
        manager = RedisManager("redis://localhost:6379/5")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='["tesla", "sustainability"]')
        mock_redis.set = AsyncMock()
        manager._redis = mock_redis

        # Set
        await manager.set_seo_keywords("tenant-1", ["tesla", "sustainability"])
        mock_redis.set.assert_called_once()

        # Get
        result = await manager.get_seo_keywords("tenant-1")
        assert result == ["tesla", "sustainability"]

        await manager.close()


class TestResultCache:
    """Result cache tests."""

    async def test_result_cache_roundtrip(self) -> None:
        manager = RedisManager("redis://localhost:6379/5")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"blog_content": "# Test"}')
        mock_redis.set = AsyncMock()
        manager._redis = mock_redis

        # Set
        await manager.set_cached_result("key-1", {"blog_content": "# Test"})
        mock_redis.set.assert_called_once()

        # Get
        result = await manager.get_cached_result("key-1")
        assert result == {"blog_content": "# Test"}

        await manager.close()


class TestRateLimit:
    """Rate limiting tests."""

    async def test_rate_limit(self) -> None:
        manager = RedisManager("redis://localhost:6379/5")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        manager._redis = mock_redis

        allowed = await manager.check_rate_limit("tenant-1", limit=10)
        assert allowed is True
        mock_redis.incr.assert_called_once()

        await manager.close()

    async def test_rate_limit_exceeded(self) -> None:
        manager = RedisManager("redis://localhost:6379/5")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=11)
        manager._redis = mock_redis

        allowed = await manager.check_rate_limit("tenant-1", limit=10)
        assert allowed is False

        await manager.close()

    async def test_redis_error_returns_true(self) -> None:
        """On Redis failure, rate limit check should fail open."""
        manager = RedisManager("redis://localhost:6379/5")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager._redis = mock_redis

        allowed = await manager.check_rate_limit("tenant-1", limit=10)
        assert allowed is True

        await manager.close()
