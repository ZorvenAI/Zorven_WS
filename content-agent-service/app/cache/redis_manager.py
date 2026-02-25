"""
Redis manager — caching and rate limiting for content operations.

Key patterns:
  content:seo:{tenant_id}:targets   — Cached SEO keywords (4h TTL)
  content:result:{md5(key)}         — Cached blog results (4h TTL)
  content:rate:{tenant_id}          — Rate limit counter (60s TTL)

All operations degrade gracefully on Redis failure.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL constants
SEO_CACHE_TTL = 4 * 60 * 60  # 4 hours
RESULT_CACHE_TTL = 4 * 60 * 60  # 4 hours
RATE_LIMIT_TTL = 60  # 1 minute


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

    # --- SEO Keywords Cache ---

    async def get_seo_keywords(self, tenant_id: str) -> Optional[list[str]]:
        """Get cached SEO keywords for a tenant."""
        try:
            r = await self._get_redis()
            key = f"content:seo:{tenant_id}:targets"
            data = await r.get(key)
            if data is not None:
                logger.debug("SEO keyword cache HIT for tenant: %s", tenant_id)
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_seo_keywords: %s", exc)
            return None

    async def set_seo_keywords(
        self, tenant_id: str, keywords: list[str], ttl: int = SEO_CACHE_TTL
    ) -> None:
        """Cache SEO keywords with configurable TTL."""
        try:
            r = await self._get_redis()
            key = f"content:seo:{tenant_id}:targets"
            await r.set(key, json.dumps(keywords), ex=ttl)
            logger.debug("SEO keyword cache SET for tenant: %s", tenant_id)
        except Exception as exc:
            logger.warning("Redis error in set_seo_keywords: %s", exc)

    # --- Result Cache ---

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Get cached blog result."""
        try:
            r = await self._get_redis()
            key = f"content:result:{self._hash(cache_key)}"
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
        """Cache blog result with configurable TTL."""
        try:
            r = await self._get_redis()
            key = f"content:result:{self._hash(cache_key)}"
            await r.set(key, json.dumps(data), ex=ttl)
            logger.debug("Result cache SET for key: %s", cache_key[:50])
        except Exception as exc:
            logger.warning("Redis error in set_cached_result: %s", exc)

    # --- Rate Limiting ---

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """
        Check if a tenant is within their rate limit.

        Returns True if the request is allowed, False if rate limit exceeded.
        Uses INCR + EXPIRE pattern with 1-minute window.
        """
        try:
            r = await self._get_redis()
            key = f"content:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            # On Redis failure, allow the request (fail open)
            return True
