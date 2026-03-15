"""Feedback registry backed by Redis Sorted Sets and Hashes.

Key patterns:
- voca:<tid>:registry:feedback       — Sorted Set (score=timestamp)
- voca:<tid>:registry:themes         — Hash (theme_slug → JSON)
- voca:<tid>:registry:sentiment_daily — Sorted Set (180d TTL)
- voca:<tid>:registry:nps_monthly    — Sorted Set (365d TTL)
- voca:<tid>:registry:last_ingestion — String
- voca:<tid>:registry:last_synthesis — String
- voca:<tid>:data_coverage_history   — Sorted Set (365d TTL)
"""

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class FeedbackRegistry:
    """Redis-backed registry for VoC feedback data."""

    def __init__(
        self,
        redis_client: Any = None,
        event_emitter: Any = None,
    ) -> None:
        self._redis = redis_client
        self._emitter = event_emitter

    # ── Feedback Items ──

    async def add_feedback(
        self, tenant_id: str, feedback: Any
    ) -> None:
        """Add a feedback item to the registry."""
        if not self._redis:
            return
        try:
            key = f"voca:{tenant_id}:registry:feedback"
            member = feedback.model_dump_json()
            score = time.time()
            await self._redis.zadd(key, {member: score})
        except Exception as exc:
            logger.warning("Failed to add feedback: %s", exc)

    async def get_feedback_count(self, tenant_id: str) -> int:
        """Get total feedback count for a tenant."""
        if not self._redis:
            return 0
        try:
            key = f"voca:{tenant_id}:registry:feedback"
            return await self._redis.zcard(key)
        except Exception as exc:
            logger.warning("Failed to get feedback count: %s", exc)
            return 0

    async def get_recent_feedback(
        self, tenant_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get most recent feedback items."""
        if not self._redis:
            return []
        try:
            key = f"voca:{tenant_id}:registry:feedback"
            items = await self._redis.zrevrange(key, 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as exc:
            logger.warning("Failed to get recent feedback: %s", exc)
            return []

    # ── Theme Clusters ──

    async def upsert_theme(
        self, tenant_id: str, theme_slug: str, theme_data: dict[str, Any]
    ) -> None:
        """Upsert a theme cluster in the registry."""
        if not self._redis:
            return
        try:
            key = f"voca:{tenant_id}:registry:themes"
            await self._redis.hset(key, theme_slug, json.dumps(theme_data))
        except Exception as exc:
            logger.warning("Failed to upsert theme: %s", exc)

    async def get_theme(
        self, tenant_id: str, theme_slug: str
    ) -> dict[str, Any] | None:
        """Get a single theme cluster."""
        if not self._redis:
            return None
        try:
            key = f"voca:{tenant_id}:registry:themes"
            data = await self._redis.hget(key, theme_slug)
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Failed to get theme: %s", exc)
            return None

    async def get_all_themes(
        self, tenant_id: str
    ) -> dict[str, dict[str, Any]]:
        """Get all theme clusters."""
        if not self._redis:
            return {}
        try:
            key = f"voca:{tenant_id}:registry:themes"
            raw = await self._redis.hgetall(key)
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning("Failed to get themes: %s", exc)
            return {}

    # ── Sentiment Daily ──

    async def add_daily_sentiment(
        self, tenant_id: str, date_str: str, sentiment_data: dict[str, Any]
    ) -> None:
        """Add daily sentiment data point."""
        if not self._redis:
            return
        try:
            key = f"voca:{tenant_id}:registry:sentiment_daily"
            member = json.dumps({"date": date_str, **sentiment_data})
            score = time.time()
            await self._redis.zadd(key, {member: score})
            # Set 180d TTL if not already set
            ttl = await self._redis.ttl(key)
            if ttl < 0:
                await self._redis.expire(key, 15552000)  # 180 days
        except Exception as exc:
            logger.warning("Failed to add daily sentiment: %s", exc)

    # ── NPS Monthly ──

    async def add_monthly_nps(
        self, tenant_id: str, period: str, nps_data: dict[str, Any]
    ) -> None:
        """Add monthly NPS data point."""
        if not self._redis:
            return
        try:
            key = f"voca:{tenant_id}:registry:nps_monthly"
            member = json.dumps({"period": period, **nps_data})
            score = time.time()
            await self._redis.zadd(key, {member: score})
            ttl = await self._redis.ttl(key)
            if ttl < 0:
                await self._redis.expire(key, 31536000)  # 365 days
        except Exception as exc:
            logger.warning("Failed to add monthly NPS: %s", exc)

    async def get_nps_history(
        self, tenant_id: str, limit: int = 12
    ) -> list[dict[str, Any]]:
        """Get NPS history (most recent first)."""
        if not self._redis:
            return []
        try:
            key = f"voca:{tenant_id}:registry:nps_monthly"
            items = await self._redis.zrevrange(key, 0, limit - 1)
            return [json.loads(item) for item in items]
        except Exception as exc:
            logger.warning("Failed to get NPS history: %s", exc)
            return []

    # ── Data Coverage ──

    async def add_coverage_score(
        self, tenant_id: str, score: float, channels: list[str], mode: str
    ) -> None:
        """Add data coverage score data point."""
        if not self._redis:
            return
        try:
            key = f"voca:{tenant_id}:data_coverage_history"
            member = json.dumps({
                "score": score,
                "channels": channels,
                "mode": mode,
            })
            ts = time.time()
            await self._redis.zadd(key, {member: ts})
            ttl = await self._redis.ttl(key)
            if ttl < 0:
                await self._redis.expire(key, 31536000)
        except Exception as exc:
            logger.warning("Failed to add coverage score: %s", exc)

    # ── Timestamps ──

    async def set_last_synthesis(self, tenant_id: str, ts: str) -> None:
        if not self._redis:
            return
        try:
            await self._redis.set(
                f"voca:{tenant_id}:registry:last_synthesis", ts
            )
        except Exception as exc:
            logger.warning("Failed to set last synthesis: %s", exc)

    async def get_last_synthesis(self, tenant_id: str) -> str | None:
        if not self._redis:
            return None
        try:
            return await self._redis.get(
                f"voca:{tenant_id}:registry:last_synthesis"
            )
        except Exception as exc:
            logger.warning("Failed to get last synthesis: %s", exc)
            return None
