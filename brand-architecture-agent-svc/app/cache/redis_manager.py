"""Async Redis manager for the Brand Architecture Agent service.

Key patterns (prefix: baa, Redis DB 17):
- baa:{tid}:result:{md5}                    — Result cache (4h TTL)
- baa:rate:{tenant_id}                      — Rate limit counter (60s TTL)
- baa:{tid}:idempotency:{key}               — Dedup (24h TTL)
- baa:{tid}:registry:architecture            — Current architecture (Hash, no TTL)
- baa:{tid}:registry:architecture_version:{v}— Versioned snapshots (JSON, 365d TTL)
- baa:{tid}:registry:portfolio               — Product portfolio (Hash, no TTL)
- baa:{tid}:session:{sid}                    — Session state (Hash, 1h TTL)
- baa:{tid}:company_context                  — Cached Company model (JSON, 1h TTL)

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

    # -- Result Cache --

    @staticmethod
    def _cache_key(prompt: str, config: dict, tenant_id: str = "default") -> str:
        """Generate deterministic, tenant-scoped cache key."""
        raw = f"{tenant_id}:{prompt}:{json.dumps(config, sort_keys=True)}"
        return f"baa:{tenant_id}:result:{hashlib.md5(raw.encode()).hexdigest()}"

    async def get_cached_result(
        self, prompt: str, config: dict, tenant_id: str = "default"
    ) -> dict[str, Any] | None:
        """Retrieve cached architecture result."""
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
        """Cache an architecture result."""
        if not self._redis:
            return
        try:
            key = self._cache_key(prompt, config, tenant_id)
            await self._redis.setex(key, settings.RESULT_CACHE_TTL, json.dumps(result))
            logger.info("Cached result: %s (TTL=%ds)", key, settings.RESULT_CACHE_TTL)
        except Exception as exc:
            logger.warning("Redis set failed (fail-open): %s", exc)

    # -- Rate Limiting --

    async def check_rate_limit(self, tenant_id: str) -> bool:
        """Check rate limit. Returns True if request is allowed."""
        if not self._redis:
            return True  # fail-open
        try:
            key = f"baa:rate:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
            return count <= settings.RATE_LIMIT_PER_MINUTE
        except Exception as exc:
            logger.warning("Rate limit check failed (fail-open): %s", exc)
            return True

    # -- Architecture Registry --

    async def save_architecture(
        self, tenant_id: str, architecture_data: dict[str, Any]
    ) -> None:
        """Save current architecture to registry (no TTL)."""
        if not self._redis:
            return
        try:
            key = f"baa:{tenant_id}:registry:architecture"
            await self._redis.set(key, json.dumps(architecture_data))
        except Exception as exc:
            logger.warning("Redis architecture save failed: %s", exc)

    async def get_architecture(self, tenant_id: str) -> dict[str, Any] | None:
        """Get current architecture from registry."""
        if not self._redis:
            return None
        try:
            key = f"baa:{tenant_id}:registry:architecture"
            data = await self._redis.get(key)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis architecture get failed: %s", exc)
            return None

    async def save_portfolio(
        self, tenant_id: str, portfolio_data: dict[str, Any]
    ) -> None:
        """Save product portfolio to registry (no TTL)."""
        if not self._redis:
            return
        try:
            key = f"baa:{tenant_id}:registry:portfolio"
            await self._redis.set(key, json.dumps(portfolio_data))
        except Exception as exc:
            logger.warning("Redis portfolio save failed: %s", exc)
