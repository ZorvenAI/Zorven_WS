"""Async Redis manager for deduplication and rate limiting.

All operations fail-open: Redis errors are logged but never bubble up
to callers, ensuring the service continues to function without Redis.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Dedup TTL in seconds (from settings.DEDUP_TTL_HOURS)
DEDUP_TTL = settings.DEDUP_TTL_HOURS * 60 * 60

# Rate limit window
RATE_LIMIT_TTL = 60  # 1 minute


class RedisManager:
    """Async Redis client for deduplication and rate limiting."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def check_dedup(self, tenant_id: str, file_hash: str) -> bool:
        """Check if a file has already been ingested.

        Returns True if the file is a duplicate (already seen).
        Returns False on Redis errors (fail-open: allow processing).
        """
        try:
            r = await self._get_redis()
            key = f"uploader:dedupe:{tenant_id}:{file_hash}"
            return await r.exists(key) > 0
        except Exception as exc:
            logger.warning("Redis dedup check failed (fail-open): %s", exc)
            return False

    async def mark_ingested(self, tenant_id: str, file_hash: str) -> None:
        """Mark a file as ingested in the dedup store.

        Uses SET with NX (only set if not exists) and TTL.
        """
        try:
            r = await self._get_redis()
            key = f"uploader:dedupe:{tenant_id}:{file_hash}"
            await r.set(key, "1", ex=DEDUP_TTL, nx=True)
        except Exception as exc:
            logger.warning("Redis mark_ingested failed: %s", exc)

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """Check if the tenant has exceeded the rate limit.

        Returns True if within limit, False if exceeded.
        Fails open (returns True) on Redis errors.
        """
        try:
            r = await self._get_redis()
            key = f"uploader:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis rate limit check failed (fail-open): %s", exc)
            return True

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception as exc:
                logger.warning("Error closing Redis: %s", exc)
            self._redis = None

    @staticmethod
    def hash_uri(uri: str) -> str:
        """Compute SHA256 hash of a GCS URI for dedup key."""
        return hashlib.sha256(uri.encode()).hexdigest()
