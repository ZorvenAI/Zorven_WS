"""
Redis manager - caching and rate limiting for competitive intelligence operations.

Key patterns:
  cia:result:{hash}                        - Analysis result cache (4h TTL)
  cia:profile:{tenant_id}:{slug}           - Competitor profile (24h TTL)
  cia:rate:{tenant_id}                     - Rate limit counter (1 min TTL)
  cia:{tenant_id}:registry:competitors     - Competitor registry (persistent Hash)
  cia:{tenant_id}:registry:snapshots:{slug} - Competitor snapshots (90 day TTL)

All operations degrade gracefully on Redis failure.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Default TTL constants (overridable via Settings)
_DEFAULT_RESULT_TTL = 4 * 60 * 60  # 4 hours
_DEFAULT_PROFILE_TTL = 24 * 60 * 60  # 24 hours
_DEFAULT_SNAPSHOT_TTL = 90 * 24 * 60 * 60  # 90 days
RATE_LIMIT_TTL = 60  # 1 minute


class RedisManager:
    """Async Redis manager for caching and rate limiting."""

    def __init__(
        self,
        redis_url: str,
        result_cache_ttl: int = _DEFAULT_RESULT_TTL,
        profile_cache_ttl: int = _DEFAULT_PROFILE_TTL,
    ) -> None:
        self.redis_url = redis_url
        self.result_cache_ttl = result_cache_ttl
        self.profile_cache_ttl = profile_cache_ttl
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
        """Get cached analysis result."""
        try:
            r = await self._get_redis()
            key = f"cia:result:{cache_key}"
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
        """Cache analysis result."""
        try:
            r = await self._get_redis()
            key = f"cia:result:{cache_key}"
            await r.set(key, json.dumps(result), ex=ttl or self.result_cache_ttl)
            logger.debug("Result cache SET for key: %s", cache_key[:16])
        except Exception as exc:
            logger.warning("Redis error in set_cached_result: %s", exc)

    # --- Competitor Profile Cache ---

    async def get_cached_profile(
        self, tenant_id: str, slug: str
    ) -> Optional[dict[str, Any]]:
        """Get cached competitor profile."""
        try:
            r = await self._get_redis()
            key = f"cia:profile:{tenant_id}:{slug}"
            data = await r.get(key)
            if data is not None:
                logger.debug("Profile cache HIT: %s/%s", tenant_id, slug)
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_profile: %s", exc)
            return None

    async def set_cached_profile(
        self,
        tenant_id: str,
        slug: str,
        data: dict[str, Any],
    ) -> None:
        """Cache competitor profile with 24-hour TTL."""
        try:
            r = await self._get_redis()
            key = f"cia:profile:{tenant_id}:{slug}"
            await r.set(key, json.dumps(data), ex=self.profile_cache_ttl)
            logger.debug("Profile cache SET: %s/%s", tenant_id, slug)
        except Exception as exc:
            logger.warning("Redis error in set_cached_profile: %s", exc)

    # --- Rate Limiting ---

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """
        Check if a tenant is within their rate limit.

        Returns True if the request is allowed, False if rate limit exceeded.
        Uses INCR + EXPIRE pattern with 1-minute window.
        """
        try:
            r = await self._get_redis()
            key = f"cia:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            # On Redis failure, allow the request (fail open)
            return True

    # --- Idempotency ---

    async def check_idempotency(self, idempotency_key: str) -> bool:
        """Check if an idempotency key exists. Returns True if already processed."""
        try:
            r = await self._get_redis()
            key = f"cia:idempotent:{idempotency_key}"
            exists = await r.exists(key)
            return bool(exists)
        except Exception as exc:
            logger.warning("Redis error in check_idempotency: %s", exc)
            return False

    async def set_idempotency(self, idempotency_key: str, ttl: int = 86400) -> None:
        """Set an idempotency key with TTL (default 24h)."""
        try:
            r = await self._get_redis()
            key = f"cia:idempotent:{idempotency_key}"
            await r.set(key, "1", ex=ttl)
        except Exception as exc:
            logger.warning("Redis error in set_idempotency: %s", exc)
