"""Async Redis manager — caching, rate limiting, session management.

Follows the fail-open pattern: all Redis errors are caught and logged,
never propagated. The service continues without caching if Redis is
unavailable.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisManager:
    """Lightweight async Redis wrapper for Odoo MCP Server."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    # ── Rate limiting ──

    async def check_rate_limit(self, key: str, limit: Optional[int] = None) -> bool:
        """Return True if the key is within the rate limit."""
        if limit is None:
            limit = settings.RATE_LIMIT_PER_MINUTE
        try:
            r = await self._get_redis()
            rate_key = f"odoo_mcp:rate:{key}"
            count = await r.incr(rate_key)
            if count == 1:
                await r.expire(rate_key, 60)
            return count <= limit
        except Exception:
            logger.warning("Redis rate-limit check failed — allowing request")
            return True

    # ── Schema caching ──

    async def get_schema(self, tenant_id: str, model: str) -> Optional[dict[str, Any]]:
        """Get cached Odoo model schema."""
        try:
            r = await self._get_redis()
            key = f"odoo_mcp:schema:{tenant_id}:{model}"
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception:
            logger.warning("Redis schema read failed for %s:%s", tenant_id, model)
        return None

    async def set_schema(
        self, tenant_id: str, model: str, schema: dict[str, Any]
    ) -> None:
        """Cache Odoo model schema."""
        try:
            r = await self._get_redis()
            key = f"odoo_mcp:schema:{tenant_id}:{model}"
            await r.set(key, json.dumps(schema), ex=settings.SCHEMA_CACHE_TTL)
        except Exception:
            logger.warning("Redis schema write failed for %s:%s", tenant_id, model)

    # ── Session caching ──

    async def get_session(self, tenant_id: str) -> Optional[dict[str, Any]]:
        """Get cached Odoo session (uid, db, etc.)."""
        try:
            r = await self._get_redis()
            key = f"odoo_mcp:session:{tenant_id}"
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception:
            logger.warning("Redis session read failed for %s", tenant_id)
        return None

    async def set_session(self, tenant_id: str, session: dict[str, Any]) -> None:
        """Cache Odoo session."""
        try:
            r = await self._get_redis()
            key = f"odoo_mcp:session:{tenant_id}"
            await r.set(key, json.dumps(session), ex=settings.SESSION_CACHE_TTL)
        except Exception:
            logger.warning("Redis session write failed for %s", tenant_id)

    # ── RBAC caching ──

    async def get_rbac(self, tenant_id: str, role: str) -> Optional[dict[str, Any]]:
        """Get cached RBAC policy for tenant role."""
        try:
            r = await self._get_redis()
            key = f"odoo_mcp:rbac:{tenant_id}:{role}"
            data = await r.get(key)
            if data:
                return json.loads(data)
        except Exception:
            logger.warning("Redis RBAC read failed for %s:%s", tenant_id, role)
        return None

    async def set_rbac(self, tenant_id: str, role: str, policy: dict[str, Any]) -> None:
        """Cache RBAC policy."""
        try:
            r = await self._get_redis()
            key = f"odoo_mcp:rbac:{tenant_id}:{role}"
            await r.set(key, json.dumps(policy), ex=settings.RBAC_CACHE_TTL)
        except Exception:
            logger.warning("Redis RBAC write failed for %s:%s", tenant_id, role)

    # ── Generic key-value ──

    async def get(self, key: str) -> Optional[str]:
        """Get a raw string value by key."""
        try:
            r = await self._get_redis()
            return await r.get(key)
        except Exception:
            logger.warning("Redis get failed for %s", key)
        return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """Set a raw string value with TTL (seconds)."""
        try:
            r = await self._get_redis()
            await r.set(key, value, ex=ttl)
        except Exception:
            logger.warning("Redis set failed for %s", key)

    # ── Generic caching ──

    @staticmethod
    def build_cache_key(*parts: str) -> str:
        """Deterministic cache key from normalized inputs."""
        raw = "|".join(p.lower().strip() for p in parts)
        digest = hashlib.md5(raw.encode()).hexdigest()
        return f"odoo_mcp:result:{digest}"

    async def get_cached_result(self, cache_key: str) -> Optional[dict[str, Any]]:
        """Return cached result dict or None."""
        try:
            r = await self._get_redis()
            data = await r.get(cache_key)
            if data:
                logger.info("Cache hit: %s", cache_key)
                return json.loads(data)
        except Exception:
            logger.warning("Redis cache read failed for %s", cache_key)
        return None

    async def set_cached_result(self, cache_key: str, result: dict[str, Any]) -> None:
        """Store result in cache with configured TTL."""
        try:
            r = await self._get_redis()
            await r.set(
                cache_key,
                json.dumps(result),
                ex=settings.RESULT_CACHE_TTL,
            )
        except Exception:
            logger.warning("Redis cache write failed for %s", cache_key)
