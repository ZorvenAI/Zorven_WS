"""Async Redis manager for Campaign Optimization Agent (DB 24, fail-open).

Key patterns:
- coa:{tid}:campaign:{cid}:perf_history       — List, 30d TTL
- coa:{tid}:campaign:{cid}:ctr_peak           — Hash, 30d TTL
- coa:{tid}:campaign:{cid}:last_action:{eid}  — Hash, no TTL
- coa:{tid}:campaign:{cid}:recommendations    — List, 48h TTL
- coa:{tid}:daily_action_counter              — Counter, 24h TTL
- coa:{tid}:spend_milestones:{cid}            — Set, 24h TTL
- coa:{tid}:hourly_perf:{cid}                 — Hash, 7d TTL
- tenant:{tid}:config                         — Hash, no TTL
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

PREFIX = "coa"

# TTL constants
TTL_30D = 30 * 24 * 3600
TTL_48H = 48 * 3600
TTL_24H = 24 * 3600
TTL_7D = 7 * 24 * 3600


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

    @property
    def available(self) -> bool:
        """Check if Redis is available."""
        return self._redis is not None

    # ── Performance history (List, 30d TTL) ──

    async def append_performance_history(
        self, tenant_id: str, campaign_id: str, data: dict[str, Any]
    ):
        """Append a performance snapshot to the campaign's history list."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:campaign:{campaign_id}:perf_history"
            await self._redis.rpush(key, json.dumps(data, default=str))
            await self._redis.expire(key, TTL_30D)
        except Exception as exc:
            logger.warning("Redis append_performance_history error: %s", exc)

    async def get_performance_history(
        self, tenant_id: str, campaign_id: str, limit: int = 100
    ) -> dict[str, Any]:
        """Get recent performance history for a campaign."""
        if not self._redis:
            return {}
        try:
            key = f"{PREFIX}:{tenant_id}:campaign:{campaign_id}:perf_history"
            entries = await self._redis.lrange(key, -limit, -1)
            parsed = [json.loads(e) for e in entries]
            if not parsed:
                return {}
            latest = parsed[-1] if parsed else {}
            return {
                "metrics": latest.get("metrics", {}),
                "health": latest.get("health", "unknown"),
                "trends": latest.get("trends", {}),
                "history": parsed,
            }
        except Exception as exc:
            logger.warning("Redis get_performance_history error: %s", exc)
            return {}

    # ── CTR peak tracking (Hash, 30d TTL) ──

    async def set_ctr_peak(
        self, tenant_id: str, campaign_id: str, ad_id: str, ctr: float
    ):
        """Set the peak CTR for an ad."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:campaign:{campaign_id}:ctr_peak"
            current = await self._redis.hget(key, ad_id)
            if current is None or float(current) < ctr:
                await self._redis.hset(key, ad_id, str(ctr))
                await self._redis.expire(key, TTL_30D)
        except Exception as exc:
            logger.warning("Redis set_ctr_peak error: %s", exc)

    async def get_ctr_peaks(
        self, tenant_id: str, campaign_id: str
    ) -> dict[str, float]:
        """Get all peak CTRs for a campaign's ads."""
        if not self._redis:
            return {}
        try:
            key = f"{PREFIX}:{tenant_id}:campaign:{campaign_id}:ctr_peak"
            data = await self._redis.hgetall(key)
            return {k: float(v) for k, v in data.items()}
        except Exception as exc:
            logger.warning("Redis get_ctr_peaks error: %s", exc)
            return {}

    # ── Last action tracking (Hash, no TTL) ──

    async def set_last_action(
        self,
        tenant_id: str,
        campaign_id: str,
        entity_id: str,
        action_data: dict[str, Any],
    ):
        """Record the last optimization action on an entity."""
        if not self._redis:
            return
        try:
            key = (
                f"{PREFIX}:{tenant_id}:campaign:{campaign_id}"
                f":last_action:{entity_id}"
            )
            await self._redis.hmset(
                key,
                {k: json.dumps(v, default=str) for k, v in action_data.items()},
            )
        except Exception as exc:
            logger.warning("Redis set_last_action error: %s", exc)

    async def get_last_action(
        self, tenant_id: str, campaign_id: str, entity_id: str
    ) -> dict[str, Any] | None:
        """Get the last optimization action on an entity."""
        if not self._redis:
            return None
        try:
            key = (
                f"{PREFIX}:{tenant_id}:campaign:{campaign_id}"
                f":last_action:{entity_id}"
            )
            data = await self._redis.hgetall(key)
            if not data:
                return None
            return {
                k: json.loads(v) if v.startswith(("{", "[", '"')) else v
                for k, v in data.items()
            }
        except Exception as exc:
            logger.warning("Redis get_last_action error: %s", exc)
            return None

    # ── Recommendations (List, 48h TTL) ──

    async def store_recommendation(
        self,
        tenant_id: str,
        campaign_id: str,
        recommendation: dict[str, Any],
    ):
        """Store a pending recommendation."""
        if not self._redis:
            return
        try:
            key = (
                f"{PREFIX}:{tenant_id}:campaign"
                f":{campaign_id}:recommendations"
            )
            await self._redis.rpush(
                key, json.dumps(recommendation, default=str)
            )
            await self._redis.expire(key, TTL_48H)
        except Exception as exc:
            logger.warning("Redis store_recommendation error: %s", exc)

    async def get_recommendations(
        self, tenant_id: str, campaign_id: str
    ) -> list[dict[str, Any]]:
        """Get all pending recommendations for a campaign."""
        if not self._redis:
            return []
        try:
            key = (
                f"{PREFIX}:{tenant_id}:campaign"
                f":{campaign_id}:recommendations"
            )
            entries = await self._redis.lrange(key, 0, -1)
            return [json.loads(e) for e in entries]
        except Exception as exc:
            logger.warning("Redis get_recommendations error: %s", exc)
            return []

    async def clear_recommendations(
        self, tenant_id: str, campaign_id: str
    ):
        """Clear all recommendations for a campaign."""
        if not self._redis:
            return
        try:
            key = (
                f"{PREFIX}:{tenant_id}:campaign"
                f":{campaign_id}:recommendations"
            )
            await self._redis.delete(key)
        except Exception as exc:
            logger.warning("Redis clear_recommendations error: %s", exc)

    # ── Daily action counter (Counter, 24h TTL) ──

    async def increment_action_counter(self, tenant_id: str) -> int:
        """Increment the daily action counter for a tenant.

        Returns the new count.
        """
        if not self._redis:
            return 0
        try:
            key = f"{PREFIX}:{tenant_id}:daily_action_counter"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, TTL_24H)
            return count
        except Exception as exc:
            logger.warning("Redis increment_action_counter error: %s", exc)
            return 0

    async def get_action_counter(self, tenant_id: str) -> int:
        """Get the current daily action count for a tenant."""
        if not self._redis:
            return 0
        try:
            key = f"{PREFIX}:{tenant_id}:daily_action_counter"
            val = await self._redis.get(key)
            return int(val) if val else 0
        except Exception as exc:
            logger.warning("Redis get_action_counter error: %s", exc)
            return 0

    # ── Spend milestones (Set, 24h TTL) ──

    async def add_spend_milestone(
        self, tenant_id: str, campaign_id: str, milestone: str
    ) -> bool:
        """Add a spend milestone. Returns True if newly added."""
        if not self._redis:
            return False
        try:
            key = f"{PREFIX}:{tenant_id}:spend_milestones:{campaign_id}"
            added = await self._redis.sadd(key, milestone)
            await self._redis.expire(key, TTL_24H)
            return bool(added)
        except Exception as exc:
            logger.warning("Redis add_spend_milestone error: %s", exc)
            return False

    async def get_spend_milestones(
        self, tenant_id: str, campaign_id: str
    ) -> set[str]:
        """Get all spend milestones for a campaign."""
        if not self._redis:
            return set()
        try:
            key = f"{PREFIX}:{tenant_id}:spend_milestones:{campaign_id}"
            return await self._redis.smembers(key)
        except Exception as exc:
            logger.warning("Redis get_spend_milestones error: %s", exc)
            return set()

    # ── Hourly performance (Hash, 7d TTL) ──

    async def set_hourly_perf(
        self,
        tenant_id: str,
        campaign_id: str,
        hour_key: str,
        data: dict[str, Any],
    ):
        """Set hourly performance data for a campaign."""
        if not self._redis:
            return
        try:
            key = f"{PREFIX}:{tenant_id}:hourly_perf:{campaign_id}"
            await self._redis.hset(
                key, hour_key, json.dumps(data, default=str)
            )
            await self._redis.expire(key, TTL_7D)
        except Exception as exc:
            logger.warning("Redis set_hourly_perf error: %s", exc)

    async def get_hourly_perf(
        self, tenant_id: str, campaign_id: str
    ) -> dict[str, dict[str, Any]]:
        """Get all hourly performance data for a campaign."""
        if not self._redis:
            return {}
        try:
            key = f"{PREFIX}:{tenant_id}:hourly_perf:{campaign_id}"
            data = await self._redis.hgetall(key)
            return {k: json.loads(v) for k, v in data.items()}
        except Exception as exc:
            logger.warning("Redis get_hourly_perf error: %s", exc)
            return {}

    # ── Tenant config (Hash, no TTL) ──

    async def set_tenant_config(
        self, tenant_id: str, config: dict[str, Any]
    ):
        """Store tenant optimization configuration."""
        if not self._redis:
            return
        try:
            key = f"tenant:{tenant_id}:config"
            await self._redis.hmset(
                key,
                {k: json.dumps(v, default=str) for k, v in config.items()},
            )
        except Exception as exc:
            logger.warning("Redis set_tenant_config error: %s", exc)

    async def get_tenant_config(
        self, tenant_id: str
    ) -> dict[str, Any]:
        """Get tenant optimization configuration."""
        if not self._redis:
            return {}
        try:
            key = f"tenant:{tenant_id}:config"
            data = await self._redis.hgetall(key)
            result = {}
            for k, v in data.items():
                try:
                    result[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[k] = v
            return result
        except Exception as exc:
            logger.warning("Redis get_tenant_config error: %s", exc)
            return {}

    # ── Generic JSON helpers ──

    async def set_json(
        self, key: str, data: dict[str, Any], ttl: int = 86400
    ):
        """Set a JSON value with TTL."""
        if not self._redis:
            return
        try:
            await self._redis.set(
                key, json.dumps(data, default=str), ex=ttl
            )
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
