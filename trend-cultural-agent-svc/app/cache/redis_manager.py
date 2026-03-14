"""Redis manager with fail-open semantics for TCIA.

Key patterns:
  tcia:result:{md5}                            — Result cache (2h TTL)
  tcia:rate:{tenant_id}                        — Rate limit counter (60s TTL)
  tcia:{tid}:registry:trends                   — Hash, persistent
  tcia:{tid}:registry:scores:{trend_slug}      — Sorted Set, 90d TTL
  tcia:{tid}:registry:alerts_today             — Counter, 24h TTL
  tcia:{tid}:registry:last_scan                — String, ISO-8601
  tcia:{tid}:odoo:crm_demographics             — String (JSON), 1h TTL
  tcia:{tid}:idempotency:{key}                 — String, 24h TTL
  tcia:{tid}:config:trend_scan_optimal_hour    — String
  tcia:{tid}:config:trend_history_retention_days — String
"""

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RedisManager:
    """Async Redis manager with fail-open semantics."""

    def __init__(self, redis_url: str = "", result_ttl: int = 7200) -> None:
        self._redis_url = redis_url
        self._redis: Any = None
        self._result_ttl = result_ttl

    async def connect(self) -> None:
        """Connect to Redis (fail-open if unavailable)."""
        if not self._redis_url:
            logger.info("RedisManager: no URL configured, stub mode")
            return
        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            await self._redis.ping()
            logger.info("RedisManager: connected to %s", self._redis_url)
        except Exception as exc:
            logger.warning("RedisManager: connection failed: %s", exc)
            self._redis = None

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None

    def _cache_key(self, prompt: str, config: dict, tenant_id: str) -> str:
        """Generate a cache key from prompt + config + tenant."""
        raw = f"{tenant_id}:{prompt}:{json.dumps(config, sort_keys=True)}"
        return f"tcia:result:{hashlib.md5(raw.encode()).hexdigest()}"

    async def get_cached_result(
        self, prompt: str, config: dict, tenant_id: str
    ) -> dict | None:
        """Retrieve a cached result."""
        if not self._redis:
            return None
        try:
            key = self._cache_key(prompt, config, tenant_id)
            data = await self._redis.get(key)
            if data:
                logger.info("Cache hit: %s", key)
                return json.loads(data)
        except Exception as exc:
            logger.warning("Cache get failed: %s", exc)
        return None

    async def cache_result(
        self, prompt: str, config: dict, result: dict, tenant_id: str
    ) -> None:
        """Cache a result with TTL."""
        if not self._redis:
            return
        try:
            key = self._cache_key(prompt, config, tenant_id)
            await self._redis.setex(key, self._result_ttl, json.dumps(result))
        except Exception as exc:
            logger.warning("Cache set failed: %s", exc)

    async def check_rate_limit(self, tenant_id: str, limit: int = 10) -> bool:
        """Check rate limit. Returns True if within limit."""
        if not self._redis:
            return True
        try:
            key = f"tcia:rate:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
            return count <= limit
        except Exception as exc:
            logger.warning("Rate limit check failed: %s", exc)
            return True

    async def check_idempotency(self, key: str) -> bool:
        """Check if an idempotency key exists. Returns True if already processed."""
        if not self._redis:
            return False
        try:
            return await self._redis.exists(f"tcia:idempotency:{key}") > 0
        except Exception as exc:
            logger.warning("Idempotency check failed: %s", exc)
            return False

    async def set_idempotency(self, key: str, ttl: int = 86400) -> None:
        """Set an idempotency key."""
        if not self._redis:
            return
        try:
            await self._redis.setex(f"tcia:idempotency:{key}", ttl, "1")
        except Exception as exc:
            logger.warning("Idempotency set failed: %s", exc)

    async def get_alert_count(self, tenant_id: str) -> int:
        """Get today's alert count for a tenant."""
        if not self._redis:
            return 0
        try:
            key = f"tcia:{tenant_id}:registry:alerts_today"
            count = await self._redis.get(key)
            return int(count) if count else 0
        except Exception as exc:
            logger.warning("Alert count get failed: %s", exc)
            return 0

    async def increment_alert_count(self, tenant_id: str) -> int:
        """Increment today's alert count."""
        if not self._redis:
            return 0
        try:
            key = f"tcia:{tenant_id}:registry:alerts_today"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 86400)  # 24h TTL
            return count
        except Exception as exc:
            logger.warning("Alert count increment failed: %s", exc)
            return 0

    async def get_last_scan(self, tenant_id: str) -> str:
        """Get the last scan timestamp for a tenant."""
        if not self._redis:
            return ""
        try:
            key = f"tcia:{tenant_id}:registry:last_scan"
            return await self._redis.get(key) or ""
        except Exception as exc:
            logger.warning("Last scan get failed: %s", exc)
            return ""

    async def set_last_scan(self, tenant_id: str, timestamp: str) -> None:
        """Set the last scan timestamp."""
        if not self._redis:
            return
        try:
            key = f"tcia:{tenant_id}:registry:last_scan"
            await self._redis.set(key, timestamp)
        except Exception as exc:
            logger.warning("Last scan set failed: %s", exc)

    async def get_tenant_config(
        self, tenant_id: str, config_key: str, default: str = ""
    ) -> str:
        """Get a tenant-specific config value."""
        if not self._redis:
            return default
        try:
            key = f"tcia:{tenant_id}:config:{config_key}"
            value = await self._redis.get(key)
            return value if value is not None else default
        except Exception as exc:
            logger.warning("Tenant config get failed: %s", exc)
            return default

    # ── Registry helpers (used by TrendRegistry) ──

    async def hset(self, key: str, field: str, value: str) -> None:
        """Hash SET."""
        if not self._redis:
            return
        await self._redis.hset(key, field, value)

    async def hget(self, key: str, field: str) -> str | None:
        """Hash GET."""
        if not self._redis:
            return None
        return await self._redis.hget(key, field)

    async def hgetall(self, key: str) -> dict[str, str]:
        """Hash GETALL."""
        if not self._redis:
            return {}
        return await self._redis.hgetall(key)

    async def hdel(self, key: str, field: str) -> int:
        """Hash DEL."""
        if not self._redis:
            return 0
        return await self._redis.hdel(key, field)

    async def hlen(self, key: str) -> int:
        """Hash LEN."""
        if not self._redis:
            return 0
        return await self._redis.hlen(key)

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        """Sorted Set ADD."""
        if not self._redis:
            return 0
        return await self._redis.zadd(key, mapping)

    async def zrangebyscore(
        self,
        key: str,
        min_score: float | str,
        max_score: float | str,
        withscores: bool = False,
    ) -> list:
        """Sorted Set range by score."""
        if not self._redis:
            return []
        return await self._redis.zrangebyscore(
            key, min_score, max_score, withscores=withscores
        )

    async def zremrangebyscore(
        self, key: str, min_score: float | str, max_score: float | str
    ) -> int:
        """Sorted Set remove range by score."""
        if not self._redis:
            return 0
        return await self._redis.zremrangebyscore(key, min_score, max_score)

    async def expire(self, key: str, seconds: int) -> None:
        """Set TTL on a key."""
        if not self._redis:
            return
        await self._redis.expire(key, seconds)
