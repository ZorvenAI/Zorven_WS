"""
Redis manager — caching and rate limiting for discovery operations.

Key patterns:
  discovery:cache:{query_hash}  — Search query results (4h TTL)
  discovery:page:{url_hash}     — Scraped page content (24h TTL)
  discovery:rate:{tenant_id}    — Rate limit counter (1 min TTL)

All operations degrade gracefully on Redis failure.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL constants
SEARCH_CACHE_TTL = 4 * 60 * 60  # 4 hours
PAGE_CACHE_TTL = 24 * 60 * 60  # 24 hours
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
            await self._redis.close()
            self._redis = None

    @staticmethod
    def _hash(value: str) -> str:
        """Generate an MD5 hash for cache key construction."""
        return hashlib.md5(value.encode()).hexdigest()

    # --- Search Query Cache ---

    async def get_cached_search(self, query: str) -> Optional[dict[str, Any]]:
        """Get cached search results for a query."""
        try:
            r = await self._get_redis()
            key = f"discovery:cache:{self._hash(query)}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Search cache HIT for query: %s", query[:50])
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_search: %s", exc)
            return None

    async def set_cached_search(self, query: str, result: dict[str, Any]) -> None:
        """Cache search results with 4-hour TTL."""
        try:
            r = await self._get_redis()
            key = f"discovery:cache:{self._hash(query)}"
            await r.set(key, json.dumps(result), ex=SEARCH_CACHE_TTL)
            logger.debug("Search cache SET for query: %s", query[:50])
        except Exception as exc:
            logger.warning("Redis error in set_cached_search: %s", exc)

    # --- Page Content Cache ---

    async def get_cached_page(self, url: str) -> Optional[str]:
        """Get cached Markdown content for a URL."""
        try:
            r = await self._get_redis()
            key = f"discovery:page:{self._hash(url)}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Page cache HIT for URL: %s", url[:80])
            return data
        except Exception as exc:
            logger.warning("Redis error in get_cached_page: %s", exc)
            return None

    async def set_cached_page(self, url: str, markdown: str) -> None:
        """Cache cleaned page content with 24-hour TTL."""
        try:
            r = await self._get_redis()
            key = f"discovery:page:{self._hash(url)}"
            await r.set(key, markdown, ex=PAGE_CACHE_TTL)
            logger.debug("Page cache SET for URL: %s", url[:80])
        except Exception as exc:
            logger.warning("Redis error in set_cached_page: %s", exc)

    # --- Rate Limiting ---

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """
        Check if a tenant is within their rate limit.

        Returns True if the request is allowed, False if rate limit exceeded.
        Uses INCR + EXPIRE pattern with 1-minute window.
        """
        try:
            r = await self._get_redis()
            key = f"discovery:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            # On Redis failure, allow the request (fail open)
            return True
