"""Async Redis manager for caching, rate limiting, and lock management."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# TTL constants (seconds)
POST_LOCK_TTL = 300  # 5 minutes — duplicate post prevention
DRAFT_TTL = 86400  # 24 hours — draft storage for EDITOR approval
RATE_LIMIT_TTL = 60  # 1 minute window
RESULT_CACHE_TTL = 3600  # 1 hour


class RedisManager:
    """Async Redis client with caching, rate-limiting, and lock helpers."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._url, decode_responses=True
            )
        return self._redis

    # ------------------------------------------------------------------
    # Post lock — prevents duplicate posts within a time window
    # ------------------------------------------------------------------

    async def acquire_post_lock(self, tenant_id: str, platform: str) -> bool:
        """Acquire a SETNX-based lock to prevent duplicate posts."""
        try:
            r = await self._get_redis()
            key = f"social:lock:{tenant_id}:{platform}"
            acquired = await r.set(key, "1", nx=True, ex=POST_LOCK_TTL)
            return bool(acquired)
        except Exception as exc:
            logger.warning("Redis error in acquire_post_lock: %s", exc)
            return True  # Fail open

    async def release_post_lock(self, tenant_id: str, platform: str) -> None:
        """Release a post lock."""
        try:
            r = await self._get_redis()
            key = f"social:lock:{tenant_id}:{platform}"
            await r.delete(key)
        except Exception as exc:
            logger.warning("Redis error in release_post_lock: %s", exc)

    # ------------------------------------------------------------------
    # Draft storage — for EDITOR role (awaiting admin approval)
    # ------------------------------------------------------------------

    async def store_draft(
        self,
        job_id: str,
        platform: str,
        draft_data: dict[str, Any],
        ttl: int = DRAFT_TTL,
    ) -> None:
        """Store a draft post for later approval."""
        try:
            r = await self._get_redis()
            key = f"social:draft:{job_id}:{platform}"
            await r.set(key, json.dumps(draft_data), ex=ttl)
        except Exception as exc:
            logger.warning("Redis error in store_draft: %s", exc)

    async def get_draft(
        self, job_id: str, platform: str
    ) -> dict[str, Any] | None:
        """Retrieve a stored draft."""
        try:
            r = await self._get_redis()
            key = f"social:draft:{job_id}:{platform}"
            raw = await r.get(key)
            if raw:
                return json.loads(raw)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_draft: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """Return True if the tenant is within the rate limit."""
        try:
            r = await self._get_redis()
            key = f"social:rate:{tenant_id}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_TTL)
            return count <= limit
        except Exception as exc:
            logger.warning("Redis error in check_rate_limit: %s", exc)
            return True  # Fail open

    # ------------------------------------------------------------------
    # Result cache
    # ------------------------------------------------------------------

    async def get_cached_result(self, key: str) -> dict[str, Any] | None:
        """Return cached result or None."""
        try:
            r = await self._get_redis()
            cache_key = f"social:result:{hashlib.md5(key.encode()).hexdigest()}"
            raw = await r.get(cache_key)
            if raw:
                return json.loads(raw)
            return None
        except Exception as exc:
            logger.warning("Redis error in get_cached_result: %s", exc)
            return None

    async def set_cached_result(
        self,
        key: str,
        data: dict[str, Any],
        ttl: int = RESULT_CACHE_TTL,
    ) -> None:
        """Cache a result."""
        try:
            r = await self._get_redis()
            cache_key = f"social:result:{hashlib.md5(key.encode()).hexdigest()}"
            await r.set(cache_key, json.dumps(data), ex=ttl)
        except Exception as exc:
            logger.warning("Redis error in set_cached_result: %s", exc)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
