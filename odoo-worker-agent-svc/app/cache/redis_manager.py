"""
Redis manager — caching and rate limiting for Odoo worker operations.

Key patterns:
  odoo_worker:result:{md5(key)}   — Cached execution results (4h TTL)
  odoo_worker:rate:{tenant_id}    — Rate limit counter (60s TTL)
  odoo_worker:persona:{md5(key)}  — Cached persona resolutions (1h TTL)

All operations degrade gracefully on Redis failure.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL constants
RESULT_CACHE_TTL = 4 * 60 * 60  # 4 hours
RATE_LIMIT_TTL = 60  # 1 minute
PERSONA_CACHE_TTL = 60 * 60  # 1 hour


class RedisManager:
    """Async Redis manager for caching and rate limiting."""

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

    @staticmethod
    def _hash(value: str) -> str:
        """Generate an MD5 hash for cache key construction."""
        return hashlib.md5(value.encode()).hexdigest()

    # --- Result Cache ---

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Get a cached execution result."""
        try:
            r = await self._get_redis()
            key = f"odoo_worker:result:{self._hash(cache_key)}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Result cache HIT for key: %s", cache_key[:50])
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_result: %s", exc)
            return None

    async def set_cached_result(
        self, cache_key: str, data: dict[str, Any], ttl: int = RESULT_CACHE_TTL
    ) -> None:
        """Cache an execution result."""
        try:
            r = await self._get_redis()
            key = f"odoo_worker:result:{self._hash(cache_key)}"
            await r.set(key, json.dumps(data), ex=ttl)
        except Exception as exc:
            logger.warning("Redis error in set_cached_result: %s", exc)

    # --- Persona Cache ---

    async def get_cached_persona(self, prompt_key: str) -> Optional[str]:
        """Get a cached persona resolution."""
        try:
            r = await self._get_redis()
            key = f"odoo_worker:persona:{self._hash(prompt_key)}"
            return await r.get(key)
        except Exception as exc:
            logger.warning("Redis error in get_cached_persona: %s", exc)
            return None

    async def set_cached_persona(
        self, prompt_key: str, persona_name: str, ttl: int = PERSONA_CACHE_TTL
    ) -> None:
        """Cache a persona resolution."""
        try:
            r = await self._get_redis()
            key = f"odoo_worker:persona:{self._hash(prompt_key)}"
            await r.set(key, persona_name, ex=ttl)
        except Exception as exc:
            logger.warning("Redis error in set_cached_persona: %s", exc)

    # --- Rate Limiting ---

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """
        INCR + EXPIRE pattern with 1-minute window.
        Returns True if allowed, False if rate limit exceeded.
        Fails open on Redis error.
        """
        try:
            r = await self._get_redis()
            key = f"odoo_worker:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            return True  # fail open
