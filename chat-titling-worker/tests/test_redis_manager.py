"""Tests for RedisManager."""

from unittest.mock import AsyncMock, patch, MagicMock

from app.cache.redis_manager import RedisManager


class TestRedisManager:
    """Tests for the RedisManager class."""

    async def test_mark_and_check_processed(self):
        """Round-trip dedup: mark then check."""
        manager = RedisManager("redis://localhost:6379/4")

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.set = AsyncMock()
        manager._redis = mock_redis

        await manager.mark_processed("session-123")
        mock_redis.set.assert_called_once_with(
            "titling:processed:session-123", "1", ex=86400
        )

        result = await manager.is_processed("session-123")
        assert result is True
        mock_redis.exists.assert_called_once_with("titling:processed:session-123")

    async def test_not_processed_returns_false(self):
        """Session not in Redis returns False."""
        manager = RedisManager("redis://localhost:6379/4")

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        manager._redis = mock_redis

        result = await manager.is_processed("new-session")
        assert result is False

    async def test_redis_error_returns_false(self):
        """Fail-open: Redis error returns False for is_processed."""
        manager = RedisManager("redis://localhost:6379/4")

        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(side_effect=Exception("Connection refused"))
        manager._redis = mock_redis

        result = await manager.is_processed("session-123")
        assert result is False

    async def test_mark_processed_error_is_non_fatal(self):
        """Redis error in mark_processed doesn't raise."""
        manager = RedisManager("redis://localhost:6379/4")

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Connection refused"))
        manager._redis = mock_redis

        # Should not raise
        await manager.mark_processed("session-123")

    async def test_close(self):
        """Close tears down the Redis connection."""
        manager = RedisManager("redis://localhost:6379/4")

        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.close()
        mock_redis.aclose.assert_called_once()
        assert manager._redis is None
