"""Async Redis manager for CAA service (DB 21, fail-open)."""

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
            key = f"caa:{tenant_id}:result:{prompt_hash}"
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
            key = f"caa:{tenant_id}:result:{prompt_hash}"
            await self._redis.set(
                key,
                json.dumps(result, default=str),
                ex=settings.RESULT_CACHE_TTL,
            )
        except Exception as exc:
            logger.warning("Redis cache_result error: %s", exc)

    async def set_json(self, key: str, data: dict[str, Any], ttl: int = 86400):
        """Set a JSON value with TTL."""
        if not self._redis:
            return
        try:
            await self._redis.set(key, json.dumps(data, default=str), ex=ttl)
        except Exception as exc:
            logger.warning("Redis set_json error: %s", exc)

    async def get_json(self, key: str) -> dict[str, Any] | None:
        """Get a JSON value."""
        if not self._redis:
            return None
        try:
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_json error: %s", exc)
            return None

    # ── Rate limiting ──

    async def check_rate_limit(self, tenant_id: str) -> bool:
        """Check if tenant is within rate limits."""
        if not self._redis:
            return True
        try:
            key = f"caa:rate:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
            return count <= 30
        except Exception:
            return True

    # ── Blueprint registry ──

    _BLUEPRINT_TTL = 60 * 60 * 24 * 7  # 7 days

    async def save_blueprint(
        self,
        tenant_id: str,
        job_id: str,
        blueprint_data: dict[str, Any],
    ):
        """Save blueprint results to registry with 7-day TTL."""
        if not self._redis:
            return
        try:
            key = f"caa:{tenant_id}:registry:campaign:{job_id}"
            await self._redis.set(
                key,
                json.dumps(blueprint_data, default=str),
                ex=self._BLUEPRINT_TTL,
            )
            # Also update latest pointer for quick lookups
            latest_key = f"caa:{tenant_id}:registry:latest"
            await self._redis.set(latest_key, job_id, ex=self._BLUEPRINT_TTL)
        except Exception as exc:
            logger.warning("Redis save_blueprint error: %s", exc)

    async def get_blueprint(
        self,
        tenant_id: str,
        job_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get blueprint results from registry by job_id or latest."""
        if not self._redis:
            return None
        try:
            if not job_id:
                latest_key = f"caa:{tenant_id}:registry:latest"
                job_id = await self._redis.get(latest_key)
                if not job_id:
                    return None
                job_id = job_id.decode() if isinstance(job_id, bytes) else job_id
            key = f"caa:{tenant_id}:registry:campaign:{job_id}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis get_blueprint error: %s", exc)
            return None

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """Generate MD5 hash of prompt for cache key."""
        return hashlib.md5(prompt.encode()).hexdigest()

    @staticmethod
    def hash_inputs(prompt: str, **context: Any) -> str:
        """Generate MD5 hash of prompt + context for cache key."""
        payload = json.dumps({"prompt": prompt, **context}, sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()
