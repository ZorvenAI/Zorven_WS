"""Async Redis manager for caching and rate limiting."""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisManager:
    """Async Redis client with fail-open semantics."""

    def __init__(self, redis_url: str, result_cache_ttl: int = 14400) -> None:
        self.redis_url = redis_url
        self.result_cache_ttl = result_cache_ttl
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> aioredis.Redis:
        """Initialize and return the Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def _get_redis(self) -> aioredis.Redis:
        """Lazy connection initialization."""
        return await self.connect()

    @property
    def client(self) -> Optional[aioredis.Redis]:
        """Return the raw Redis client for health checks."""
        return self._redis

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    @staticmethod
    def _hash(value: str) -> str:
        """Generate MD5 hash for cache keys."""
        return hashlib.md5(value.encode()).hexdigest()

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Get cached result. Returns None on any error (fail-open)."""
        try:
            r = await self._get_redis()
            data = await r.get(f"poi:result:{cache_key}")
            if data is not None:
                logger.debug("Cache HIT: %s", cache_key[:16])
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis get error: %s", exc)
            return None

    async def set_cached_result(
        self,
        cache_key: str,
        result: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """Cache a result with TTL."""
        try:
            r = await self._get_redis()
            await r.set(
                f"poi:result:{cache_key}",
                json.dumps(result),
                ex=ttl or self.result_cache_ttl,
            )
            logger.debug("Cache SET: %s", cache_key[:16])
        except Exception as exc:
            logger.warning("Redis set error: %s", exc)

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """Check per-tenant rate limit. Returns True if allowed (fail-open)."""
        try:
            r = await self._get_redis()
            key = f"poi:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, 60)
            return count <= limit
        except Exception:
            return True
