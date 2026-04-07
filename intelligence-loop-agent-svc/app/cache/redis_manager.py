"""Async Redis manager for Intelligence Loop Agent (DB 25, fail-open).

Key patterns:
- ila:{tid}:job:{job_id}:status        — Hash, 24h TTL
- ila:{tid}:dedup:{job_id}             — String "1", 24h TTL (idempotency)
- ila:{tid}:campaign:{cid}:last_run    — Timestamp, no TTL
"""

import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "ila"
TTL_24H = 24 * 3600


class RedisManager:
    """Async Redis wrapper with fail-open semantics."""

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def connect(self):
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
        if self._redis:
            await self._redis.close()

    async def set_dedup(self, tenant_id: str, job_id: str) -> bool:
        """Atomic SETNX for idempotency. Returns True if first time."""
        if not self._redis:
            return True
        try:
            key = f"{PREFIX}:{tenant_id or 'public'}:dedup:{job_id}"
            ok = await self._redis.set(key, "1", ex=TTL_24H, nx=True)
            return bool(ok)
        except Exception as exc:
            logger.warning("Redis dedup set failed (fail-open): %s", exc)
            return True

    async def mark_status(self, tenant_id: str, job_id: str, status: str):
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id or 'public'}:job:{job_id}:status"
            await self._redis.hset(key, mapping={"status": status})
            await self._redis.expire(key, TTL_24H)
        except Exception as exc:
            logger.warning("Redis status set failed (fail-open): %s", exc)
