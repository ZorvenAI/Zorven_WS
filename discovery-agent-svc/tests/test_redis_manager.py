"""Tests for RedisManager — caching and rate limiting logic."""

from unittest.mock import AsyncMock

from app.cache.redis_manager import (
    PAGE_CACHE_TTL,
    RATE_LIMIT_TTL,
    SEARCH_CACHE_TTL,
    RedisManager,
)


class TestSearchCache:
    """Search query cache tests."""

    async def test_get_cached_search_returns_data_on_hit(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"results": [{"title": "Test"}]}')
        manager._redis = mock_redis

        result = await manager.get_cached_search("test query")
        assert result == {"results": [{"title": "Test"}]}

    async def test_get_cached_search_returns_none_on_miss(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        manager._redis = mock_redis

        result = await manager.get_cached_search("unknown query")
        assert result is None

    async def test_set_cached_search_stores_with_correct_ttl(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.set_cached_search("test query", {"results": []})
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == SEARCH_CACHE_TTL
        # Verify key pattern
        assert call_args.args[0].startswith("discovery:cache:")

    async def test_get_cached_search_returns_none_on_redis_error(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager._redis = mock_redis

        result = await manager.get_cached_search("test")
        assert result is None


class TestPageCache:
    """Page content cache tests."""

    async def test_get_cached_page_returns_markdown_on_hit(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="# Page Title\n\nContent here.")
        manager._redis = mock_redis

        result = await manager.get_cached_page("https://example.com")
        assert result == "# Page Title\n\nContent here."

    async def test_get_cached_page_returns_none_on_miss(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        manager._redis = mock_redis

        result = await manager.get_cached_page("https://unknown.com")
        assert result is None

    async def test_set_cached_page_stores_with_correct_ttl(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.set_cached_page("https://example.com", "# Content")
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args.kwargs.get("ex") == PAGE_CACHE_TTL
        assert call_args.args[0].startswith("discovery:page:")

    async def test_get_cached_page_returns_none_on_redis_error(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager._redis = mock_redis

        result = await manager.get_cached_page("https://example.com")
        assert result is None


class TestRateLimiting:
    """Per-tenant rate limiting tests."""

    async def test_rate_limit_allows_under_limit(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is True

    async def test_rate_limit_blocks_over_limit(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=11)
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is False

    async def test_rate_limit_sets_expire_on_first_increment(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        manager._redis = mock_redis

        await manager.check_rate_limit("tenant-1", limit=10)
        mock_redis.expire.assert_called_once()
        expire_args = mock_redis.expire.call_args
        assert expire_args.args[1] == RATE_LIMIT_TTL

    async def test_rate_limit_does_not_reset_expire_on_subsequent(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=5)
        manager._redis = mock_redis

        await manager.check_rate_limit("tenant-1", limit=10)
        mock_redis.expire.assert_not_called()

    async def test_rate_limit_allows_on_redis_error(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=ConnectionError("Redis down"))
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is True  # Fail open


class TestConnection:
    """Connection lifecycle tests."""

    async def test_close_closes_redis(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.close()
        mock_redis.close.assert_called_once()
        assert manager._redis is None

    async def test_close_when_not_connected(self) -> None:
        manager = RedisManager("redis://localhost:6379/2")
        await manager.close()  # Should not raise
