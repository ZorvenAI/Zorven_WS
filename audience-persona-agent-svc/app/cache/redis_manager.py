"""Async Redis manager for the Audience Persona Agent service.

Key patterns (prefix: apa, Redis DB 13):
- apa:result:{md5}                         — Result cache (4h TTL)
- apa:rate:{tenant_id}                     — Rate limit counter (60s TTL)
- apa:{tid}:odoo:survey_cache:{survey_id}  — Odoo survey cache (1h TTL)
- apa:{tid}:odoo:crm_segments              — Odoo CRM segments cache (1h TTL)
- apa:{tid}:registry:personas              — Persona registry (Hash, persistent)
- apa:{tid}:registry:version:{slug}:{ver}  — Versioned persona snapshots (180d TTL)
- apa:{tid}:idempotency:{key}              — Dedup (24h TTL)

All operations gracefully degrade on Redis failure (fail-open).
"""

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Async Redis wrapper with fail-open semantics."""

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("Redis connected: %s", settings.REDIS_URL)
        except Exception as exc:
            logger.warning("Redis connection failed (fail-open): %s", exc)
            self._redis = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    # ── Result Cache ──

    @staticmethod
    def _cache_key(prompt: str, config: dict) -> str:
        """Generate deterministic cache key from prompt + config."""
        raw = f"{prompt}:{json.dumps(config, sort_keys=True)}"
        return f"apa:result:{hashlib.md5(raw.encode()).hexdigest()}"

    async def get_cached_result(
        self, prompt: str, config: dict
    ) -> dict[str, Any] | None:
        """Retrieve cached analysis result."""
        if not self._redis:
            return None
        try:
            key = self._cache_key(prompt, config)
            data = await self._redis.get(key)
            if data:
                logger.info("Cache hit: %s", key)
                return json.loads(data)
        except Exception as exc:
            logger.warning("Redis get failed (fail-open): %s", exc)
        return None

    async def cache_result(
        self, prompt: str, config: dict, result: dict[str, Any]
    ) -> None:
        """Cache an analysis result."""
        if not self._redis:
            return
        try:
            key = self._cache_key(prompt, config)
            await self._redis.setex(key, settings.RESULT_CACHE_TTL, json.dumps(result))
            logger.info("Cached result: %s (TTL=%ds)", key, settings.RESULT_CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis set failed (fail-open): %s", exc)

    # ── Rate Limiting ──

    async def check_rate_limit(self, tenant_id: str) -> bool:
        """Check rate limit. Returns True if request is allowed."""
        if not self._redis:
            return True  # fail-open
        try:
            key = f"apa:rate:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
            return count <= settings.RATE_LIMIT_PER_MINUTE
        except Exception as exc:
            logger.warning("Rate limit check failed (fail-open): %s", exc)
            return True

    # ── Idempotency ──

    async def check_idempotency(self, key: str) -> bool:
        """Check if an operation was already processed. Returns True if new."""
        if not self._redis:
            return True
        try:
            idem_key = f"apa:idempotency:{key}"
            result = await self._redis.set(
                idem_key, "1", ex=settings.IDEMPOTENCY_TTL, nx=True
            )
            return result is not None
        except Exception as exc:
            logger.warning("Idempotency check failed (fail-open): %s", exc)
            return True

    # ── Odoo Cache ──

    async def get_odoo_survey_cache(
        self, tenant_id: str, survey_id: str
    ) -> dict[str, Any] | None:
        """Get cached Odoo survey data."""
        if not self._redis:
            return None
        try:
            key = f"apa:{tenant_id}:odoo:survey_cache:{survey_id}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis survey cache get failed: %s", exc)
            return None

    async def set_odoo_survey_cache(
        self, tenant_id: str, survey_id: str, data: dict[str, Any]
    ) -> None:
        """Cache Odoo survey data."""
        if not self._redis:
            return
        try:
            key = f"apa:{tenant_id}:odoo:survey_cache:{survey_id}"
            await self._redis.setex(
                key, settings.ODOO_SURVEY_CACHE_TTL, json.dumps(data)
            )
        except Exception as exc:
            logger.warning("Redis survey cache set failed: %s", exc)

    async def get_odoo_crm_cache(self, tenant_id: str) -> dict[str, Any] | None:
        """Get cached Odoo CRM segment data."""
        if not self._redis:
            return None
        try:
            key = f"apa:{tenant_id}:odoo:crm_segments"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis CRM cache get failed: %s", exc)
            return None

    async def set_odoo_crm_cache(self, tenant_id: str, data: dict[str, Any]) -> None:
        """Cache Odoo CRM segment data."""
        if not self._redis:
            return
        try:
            key = f"apa:{tenant_id}:odoo:crm_segments"
            await self._redis.setex(key, settings.ODOO_CRM_CACHE_TTL, json.dumps(data))
        except Exception as exc:
            logger.warning("Redis CRM cache set failed: %s", exc)
