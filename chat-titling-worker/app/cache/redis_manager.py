"""
Redis manager — deduplication for titling operations.

Key patterns:
  titling:processed:{session_id}  — Dedup flag (24h TTL)

All operations degrade gracefully on Redis failure.
"""

import logging
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL constants
DEDUP_TTL = 24 * 60 * 60  # 24 hours


class RedisManager:
    """Async Redis manager for titling deduplication."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        """Return a Redis connection, creating one if needed."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def is_processed(self, session_id: str) -> bool:
        """Check if a session has already been titled."""
        try:
            r = await self._get_redis()
            key = f"titling:processed:{session_id}"
            return await r.exists(key) > 0
        except Exception as exc:
            logger.warning("Redis error in is_processed: %s", exc)
            return False  # Fail open — allow processing

    async def mark_processed(self, session_id: str) -> None:
        """Mark a session as titled with 24h TTL."""
        try:
            r = await self._get_redis()
            key = f"titling:processed:{session_id}"
            await r.set(key, "1", ex=DEDUP_TTL)
            logger.debug("Marked session %s as processed", session_id)
        except Exception as exc:
            logger.warning("Redis error in mark_processed: %s", exc)
