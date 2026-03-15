"""Async Redis manager for the Voice of Customer Agent service.

Key patterns (prefix: voca, Redis DB 15):
- voca:{tid}:result:{md5}                    — Result cache (4h TTL)
- voca:rate:{tenant_id}                      — Rate limit counter (60s TTL)
- voca:{tid}:idempotency:{key}               — Dedup (24h TTL)
- voca:{tid}:odoo:helpdesk_cache             — Odoo helpdesk cache (30m TTL)
- voca:{tid}:odoo:survey_cache:{survey_id}   — Odoo survey cache (1h TTL)
- voca:{tid}:odoo:chatter_cache              — Odoo chatter cache (30m TTL)
- voca:{tid}:registry:feedback               — Feedback Sorted Set (persistent)
- voca:{tid}:registry:themes                 — Theme clusters Hash (persistent)
- voca:{tid}:registry:sentiment_daily        — Daily sentiment Sorted Set (180d)
- voca:{tid}:registry:nps_monthly            — Monthly NPS Sorted Set (365d)
- voca:{tid}:registry:last_ingestion         — Last ingestion timestamp
- voca:{tid}:registry:last_synthesis         — Last synthesis timestamp
- voca:{tid}:operating_mode                  — full | external_only
- voca:{tid}:hash_lookup:{sha256}            — Customer ID hash lookup (90d)
- voca:{tid}:data_coverage_history           — Coverage score Sorted Set (365d)
- voca:{tid}:config.*                        — Tenant config overrides
- voca:{tid}:ingestion_mode                  — kafka | polling | inactive

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
    def _cache_key(prompt: str, config: dict, tenant_id: str = "default") -> str:
        """Generate deterministic, tenant-scoped cache key."""
        raw = f"{tenant_id}:{prompt}:{json.dumps(config, sort_keys=True)}"
        return f"voca:{tenant_id}:result:{hashlib.md5(raw.encode()).hexdigest()}"

    async def get_cached_result(
        self, prompt: str, config: dict, tenant_id: str = "default"
    ) -> dict[str, Any] | None:
        """Retrieve cached analysis result."""
        if not self._redis:
            return None
        try:
            key = self._cache_key(prompt, config, tenant_id)
            data = await self._redis.get(key)
            if data:
                logger.info("Cache hit: %s", key)
                return json.loads(data)
        except Exception as exc:
            logger.warning("Redis get failed (fail-open): %s", exc)
        return None

    async def cache_result(
        self,
        prompt: str,
        config: dict,
        result: dict[str, Any],
        tenant_id: str = "default",
    ) -> None:
        """Cache an analysis result."""
        if not self._redis:
            return
        try:
            key = self._cache_key(prompt, config, tenant_id)
            await self._redis.setex(
                key, settings.RESULT_CACHE_TTL, json.dumps(result)
            )
            logger.info(
                "Cached result: %s (TTL=%ds)", key, settings.RESULT_CACHE_TTL
            )
        except Exception as exc:
            logger.warning("Redis set failed (fail-open): %s", exc)

    # ── Rate Limiting ──

    async def check_rate_limit(self, tenant_id: str) -> bool:
        """Check rate limit. Returns True if request is allowed."""
        if not self._redis:
            return True  # fail-open
        try:
            key = f"voca:rate:{tenant_id}"
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
            idem_key = f"voca:idempotency:{key}"
            result = await self._redis.set(
                idem_key, "1", ex=settings.IDEMPOTENCY_TTL, nx=True
            )
            return result is not None
        except Exception as exc:
            logger.warning("Idempotency check failed (fail-open): %s", exc)
            return True

    # ── Odoo Cache ──

    async def get_odoo_cache(
        self, tenant_id: str, cache_type: str, cache_id: str = ""
    ) -> dict[str, Any] | None:
        """Get cached Odoo data by type."""
        if not self._redis:
            return None
        try:
            suffix = f":{cache_id}" if cache_id else ""
            key = f"voca:{tenant_id}:odoo:{cache_type}{suffix}"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis Odoo cache get failed: %s", exc)
            return None

    async def set_odoo_cache(
        self,
        tenant_id: str,
        cache_type: str,
        data: dict[str, Any],
        cache_id: str = "",
        ttl: int | None = None,
    ) -> None:
        """Cache Odoo data by type."""
        if not self._redis:
            return
        try:
            suffix = f":{cache_id}" if cache_id else ""
            key = f"voca:{tenant_id}:odoo:{cache_type}{suffix}"
            cache_ttl = ttl or settings.ODOO_CACHE_TTL
            await self._redis.setex(key, cache_ttl, json.dumps(data))
        except Exception as exc:
            logger.warning("Redis Odoo cache set failed: %s", exc)

    # ── Tenant Config ──

    async def get_tenant_config(
        self, tenant_id: str, key: str
    ) -> str | None:
        """Get tenant-scoped configuration value."""
        if not self._redis:
            return None
        try:
            redis_key = f"voca:{tenant_id}:config.{key}"
            return await self._redis.get(redis_key)
        except Exception as exc:
            logger.warning("Redis tenant config get failed: %s", exc)
            return None

    # ── Operating Mode ──

    async def get_operating_mode(self, tenant_id: str) -> str | None:
        """Get tenant operating mode (full | external_only)."""
        if not self._redis:
            return None
        try:
            return await self._redis.get(f"voca:{tenant_id}:operating_mode")
        except Exception as exc:
            logger.warning("Redis operating mode get failed: %s", exc)
            return None

    async def set_operating_mode(self, tenant_id: str, mode: str) -> None:
        """Set tenant operating mode."""
        if not self._redis:
            return
        try:
            await self._redis.set(f"voca:{tenant_id}:operating_mode", mode)
        except Exception as exc:
            logger.warning("Redis operating mode set failed: %s", exc)

    # ── Hash Lookup (Decision #5) ──

    async def store_hash_lookup(
        self, tenant_id: str, hash_value: str, original_id: str
    ) -> None:
        """Store SHA-256 hash → customer ID mapping (90d TTL)."""
        if not self._redis:
            return
        try:
            key = f"voca:{tenant_id}:hash_lookup:{hash_value}"
            await self._redis.setex(key, settings.HASH_LOOKUP_TTL, original_id)
        except Exception as exc:
            logger.warning("Redis hash lookup store failed: %s", exc)

    async def get_hash_lookup(
        self, tenant_id: str, hash_value: str
    ) -> str | None:
        """Retrieve original customer ID from hash (ADMIN-only)."""
        if not self._redis:
            return None
        try:
            key = f"voca:{tenant_id}:hash_lookup:{hash_value}"
            return await self._redis.get(key)
        except Exception as exc:
            logger.warning("Redis hash lookup get failed: %s", exc)
            return None

    # ── Ingestion Mode ──

    async def get_ingestion_mode(self, tenant_id: str) -> str | None:
        """Get ingestion mode (kafka | polling | inactive)."""
        if not self._redis:
            return None
        try:
            return await self._redis.get(f"voca:{tenant_id}:ingestion_mode")
        except Exception as exc:
            logger.warning("Redis ingestion mode get failed: %s", exc)
            return None

    async def set_ingestion_mode(self, tenant_id: str, mode: str) -> None:
        """Set ingestion mode."""
        if not self._redis:
            return
        try:
            await self._redis.set(f"voca:{tenant_id}:ingestion_mode", mode)
        except Exception as exc:
            logger.warning("Redis ingestion mode set failed: %s", exc)
