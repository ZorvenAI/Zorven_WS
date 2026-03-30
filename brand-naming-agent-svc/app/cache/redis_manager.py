"""Async Redis manager for NTA service (DB 19, fail-open)."""

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Async Redis wrapper with fail-open semantics."""

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def connect(self):
        """Establish Redis connection (fail-open)."""
        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Redis connected: %s", settings.REDIS_URL)
        except Exception as exc:
            logger.warning("Redis unavailable (fail-open): %s", exc)
            self._redis = None

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    # ── Result caching ──

    async def get_cached_result(
        self, tenant_id: str, prompt_hash: str
    ) -> dict[str, Any] | None:
        """Get cached result by prompt hash."""
        if not self._redis:
            return None
        try:
            key = f"nta:{tenant_id}:result:{prompt_hash}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_cached_result error: %s", exc)
            return None

    async def cache_result(
        self, tenant_id: str, prompt_hash: str, result: dict[str, Any]
    ):
        """Cache result with TTL."""
        if not self._redis:
            return
        try:
            key = f"nta:{tenant_id}:result:{prompt_hash}"
            await self._redis.set(
                key, json.dumps(result, default=str), ex=settings.RESULT_CACHE_TTL
            )
        except Exception as exc:
            logger.warning("Redis cache_result error: %s", exc)

    # ── Rate limiting ──

    async def check_rate_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within rate limits."""
        if not self._redis:
            return True
        try:
            key = f"nta:rate:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
            return count <= 30
        except Exception:
            return True

    # ── Naming registry ──

    async def save_naming(
        self, tenant_id: str, naming_data: dict[str, Any]
    ):
        """Save naming results to registry (no TTL)."""
        if not self._redis:
            return
        try:
            key = f"nta:{tenant_id}:registry:naming"
            await self._redis.set(key, json.dumps(naming_data, default=str))
        except Exception as exc:
            logger.warning("Redis save_naming error: %s", exc)

    async def get_naming(
        self, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get naming results from registry."""
        if not self._redis:
            return None
        try:
            key = f"nta:{tenant_id}:registry:naming"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_naming error: %s", exc)
            return None

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """Generate MD5 hash of prompt for cache key."""
        return hashlib.md5(prompt.encode()).hexdigest()
