"""Tests for RedisManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cache.redis_manager import RedisManager


class TestRedisManager:
    """Tests for Redis dedup and rate limiting."""

    async def test_dedup_new_file_returns_false(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 0
        manager._redis = mock_redis

        result = await manager.check_dedup("tenant-1", "abc123")
        assert result is False
        mock_redis.exists.assert_called_once_with("uploader:dedupe:tenant-1:abc123")

    async def test_dedup_existing_file_returns_true(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        mock_redis.exists.return_value = 1
        manager._redis = mock_redis

        result = await manager.check_dedup("tenant-1", "abc123")
        assert result is True

    async def test_mark_ingested_sets_with_ttl(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        manager._redis = mock_redis

        await manager.mark_ingested("tenant-1", "abc123")
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args
        assert "uploader:dedupe:tenant-1:abc123" in call_kwargs[0]
        assert call_kwargs[1]["nx"] is True
        assert call_kwargs[1]["ex"] > 0

    async def test_rate_limit_within_limit(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is True

    async def test_rate_limit_exceeded(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 11
        manager._redis = mock_redis

        result = await manager.check_rate_limit("tenant-1", limit=10)
        assert result is False

    async def test_redis_error_dedup_fails_open(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        mock_redis.exists.side_effect = ConnectionError("Redis down")
        manager._redis = mock_redis

        # Should return False (allow processing) on error
        result = await manager.check_dedup("tenant-1", "abc")
        assert result is False

    async def test_redis_error_rate_limit_fails_open(self):
        manager = RedisManager("redis://localhost:6379/7")
        mock_redis = AsyncMock()
        mock_redis.incr.side_effect = ConnectionError("Redis down")
        manager._redis = mock_redis

        # Should return True (allow request) on error
        result = await manager.check_rate_limit("tenant-1")
        assert result is True

    def test_hash_uri(self):
        h1 = RedisManager.hash_uri("gs://bucket/file.pdf")
        h2 = RedisManager.hash_uri("gs://bucket/file.pdf")
        h3 = RedisManager.hash_uri("gs://bucket/other.pdf")
        assert h1 == h2  # Same URI = same hash
        assert h1 != h3  # Different URI = different hash
        assert len(h1) == 64  # SHA256 hex digest
