"""
Redis manager — caching and rate limiting for market research operations.

Key patterns:
  mra:result:{hash}                          — Research result cache (4h TTL)
  mra:economic:{indicator}:{country}:{year}  — World Bank data (24h TTL)
  mra:news:{hash}                            — News results (1h TTL)
  mra:rate:{tenant_id}                       — Rate limit counter (1 min TTL)

All operations degrade gracefully on Redis failure.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Default TTL constants (overridable via Settings)
_DEFAULT_RESEARCH_TTL = 4 * 60 * 60  # 4 hours
_DEFAULT_ECONOMIC_TTL = 24 * 60 * 60  # 24 hours
_DEFAULT_NEWS_TTL = 60 * 60  # 1 hour
RATE_LIMIT_TTL = 60  # 1 minute


class RedisManager:
    """Async Redis manager for caching and rate limiting."""

    def __init__(
        self,
        redis_url: str,
        research_cache_ttl: int = _DEFAULT_RESEARCH_TTL,
        economic_cache_ttl: int = _DEFAULT_ECONOMIC_TTL,
        news_cache_ttl: int = _DEFAULT_NEWS_TTL,
    ) -> None:
        self.redis_url = redis_url
        self.research_cache_ttl = research_cache_ttl
        self.economic_cache_ttl = economic_cache_ttl
        self.news_cache_ttl = news_cache_ttl
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

    # --- Research Result Cache ---

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Get cached research result."""
        try:
            r = await self._get_redis()
            key = f"mra:result:{cache_key}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Result cache HIT for key: %s", cache_key[:16])
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_result: %s", exc)
            return None

    async def set_cached_result(
        self, cache_key: str, result: dict[str, Any], ttl: int | None = None
    ) -> None:
        """Cache research result."""
        try:
            r = await self._get_redis()
            key = f"mra:result:{cache_key}"
            await r.set(key, json.dumps(result), ex=ttl or self.research_cache_ttl)
            logger.debug("Result cache SET for key: %s", cache_key[:16])
        except Exception as exc:
            logger.warning("Redis error in set_cached_result: %s", exc)

    # --- Economic Data Cache ---

    async def get_cached_economic(
        self, indicator: str, country: str, year: str
    ) -> Optional[dict[str, Any]]:
        """Get cached economic indicator data."""
        try:
            r = await self._get_redis()
            key = f"mra:economic:{indicator}:{country}:{year}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Economic cache HIT: %s/%s/%s", indicator, country, year)
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_economic: %s", exc)
            return None

    async def set_cached_economic(
        self,
        indicator: str,
        country: str,
        year: str,
        data: dict[str, Any],
    ) -> None:
        """Cache economic indicator data with 24-hour TTL."""
        try:
            r = await self._get_redis()
            key = f"mra:economic:{indicator}:{country}:{year}"
            await r.set(key, json.dumps(data), ex=self.economic_cache_ttl)
            logger.debug("Economic cache SET: %s/%s/%s", indicator, country, year)
        except Exception as exc:
            logger.warning("Redis error in set_cached_economic: %s", exc)

    # --- News Cache ---

    async def get_cached_news(self, query: str) -> Optional[list[dict[str, Any]]]:
        """Get cached news results."""
        try:
            r = await self._get_redis()
            key = f"mra:news:{self._hash(query)}"
            data = await r.get(key)
            if data is not None:
                logger.debug("News cache HIT for query: %s", query[:50])
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_news: %s", exc)
            return None

    async def set_cached_news(self, query: str, articles: list[dict[str, Any]]) -> None:
        """Cache news results with 1-hour TTL."""
        try:
            r = await self._get_redis()
            key = f"mra:news:{self._hash(query)}"
            await r.set(key, json.dumps(articles), ex=self.news_cache_ttl)
            logger.debug("News cache SET for query: %s", query[:50])
        except Exception as exc:
            logger.warning("Redis error in set_cached_news: %s", exc)

    # --- Rate Limiting ---

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """
        Check if a tenant is within their rate limit.

        Returns True if the request is allowed, False if rate limit exceeded.
        Uses INCR + EXPIRE pattern with 1-minute window.
        """
        try:
            r = await self._get_redis()
            key = f"mra:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            # On Redis failure, allow the request (fail open)
            return True
