"""Redis Hash + Sorted Set trend registry with velocity detection."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.registry.models import TrendRegistryEntry, TrendVelocity

logger = logging.getLogger(__name__)

_VELOCITY_THRESHOLD = 15  # Score delta to trigger velocity event


class TrendRegistry:
    """Persistent trend registry backed by Redis Hash + Sorted Set."""

    def __init__(self, redis_manager: Any, event_emitter: Any = None) -> None:
        self._redis = redis_manager
        self._events = event_emitter

    def _registry_key(self, tenant_id: str) -> str:
        return f"tcia:{tenant_id}:registry:trends"

    def _scores_key(self, tenant_id: str, slug: str) -> str:
        return f"tcia:{tenant_id}:registry:scores:{slug}"

    async def upsert_trend(
        self,
        tenant_id: str,
        slug: str,
        profile: dict[str, Any],
    ) -> TrendVelocity | None:
        """Upsert a trend profile. Returns velocity change if significant."""
        try:
            # Check for velocity change
            existing = await self.get_trend(tenant_id, slug)
            entry = TrendRegistryEntry(**profile)
            velocity = self._detect_velocity_change(existing, entry, slug)

            # Update registry Hash
            entry.last_updated = datetime.now(timezone.utc).isoformat()
            if existing:
                entry.first_seen = existing.first_seen
                entry.scan_count = existing.scan_count + 1
            else:
                entry.first_seen = entry.last_updated
                entry.scan_count = 1

            await self._redis.hset(
                self._registry_key(tenant_id),
                slug,
                json.dumps(entry.model_dump()),
            )

            # Add score to Sorted Set (score=timestamp, member=relevance_score)
            timestamp = datetime.now(timezone.utc).timestamp()
            await self._redis.zadd(
                self._scores_key(tenant_id, slug),
                {str(entry.relevance_score): timestamp},
            )

            # Set TTL on scores key
            retention_days = await self._get_retention_days(tenant_id)
            await self._redis.expire(
                self._scores_key(tenant_id, slug),
                retention_days * 86400,
            )

            # Emit velocity event
            if velocity and self._events:
                from app.events.catalog import EventType

                await self._events.emit(
                    EventType.TREND_VELOCITY_CHANGED,
                    tenant_id=tenant_id,
                    detail=velocity.model_dump(),
                )

            return velocity
        except Exception as exc:
            logger.warning("Failed to upsert trend %s: %s", slug, exc)
            return None

    async def get_trend(
        self, tenant_id: str, slug: str
    ) -> TrendRegistryEntry | None:
        """Get a single trend from the registry."""
        try:
            data = await self._redis.hget(self._registry_key(tenant_id), slug)
            if data:
                return TrendRegistryEntry(**json.loads(data))
        except Exception as exc:
            logger.warning("Failed to get trend %s: %s", slug, exc)
        return None

    async def get_all_trends(
        self, tenant_id: str
    ) -> dict[str, TrendRegistryEntry]:
        """Get all trends from the registry."""
        try:
            data = await self._redis.hgetall(self._registry_key(tenant_id))
            return {
                slug: TrendRegistryEntry(**json.loads(profile_json))
                for slug, profile_json in data.items()
            }
        except Exception as exc:
            logger.warning("Failed to get all trends: %s", exc)
            return {}

    async def delete_trend(self, tenant_id: str, slug: str) -> bool:
        """Delete a trend from the registry."""
        try:
            result = await self._redis.hdel(
                self._registry_key(tenant_id), slug
            )
            return result > 0
        except Exception as exc:
            logger.warning("Failed to delete trend %s: %s", slug, exc)
            return False

    async def trend_count(self, tenant_id: str) -> int:
        """Get the number of trends in the registry."""
        try:
            return await self._redis.hlen(self._registry_key(tenant_id))
        except Exception as exc:
            logger.warning("Failed to count trends: %s", exc)
            return 0

    async def get_score_history(
        self,
        tenant_id: str,
        slug: str,
        days: int = 90,
    ) -> list[tuple[str, float]]:
        """Returns list of (score, timestamp) from Sorted Set."""
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).timestamp()
            return await self._redis.zrangebyscore(
                self._scores_key(tenant_id, slug),
                cutoff,
                "+inf",
                withscores=True,
            )
        except Exception as exc:
            logger.warning("Failed to get score history for %s: %s", slug, exc)
            return []

    async def evict_expired_scores(
        self, tenant_id: str, slug: str, retention_days: int = 90
    ) -> int:
        """Remove scores older than retention period."""
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).timestamp()
            return await self._redis.zremrangebyscore(
                self._scores_key(tenant_id, slug), "-inf", cutoff
            )
        except Exception as exc:
            logger.warning("Failed to evict scores for %s: %s", slug, exc)
            return 0

    async def _get_retention_days(self, tenant_id: str) -> int:
        """Get tenant-configurable retention days."""
        try:
            value = await self._redis.get_tenant_config(
                tenant_id, "trend_history_retention_days", "90"
            )
            return int(value)
        except (ValueError, TypeError):
            return 90

    @staticmethod
    def _detect_velocity_change(
        existing: TrendRegistryEntry | None,
        new_entry: TrendRegistryEntry,
        slug: str,
    ) -> TrendVelocity | None:
        """Detect significant score movement."""
        if not existing:
            return TrendVelocity(
                trend_slug=slug,
                direction="new",
                delta=new_entry.relevance_score,
                old_score=0,
                new_score=new_entry.relevance_score,
            )
        delta = new_entry.relevance_score - existing.relevance_score
        if abs(delta) >= _VELOCITY_THRESHOLD:
            direction = "rising" if delta > 0 else "falling"
            return TrendVelocity(
                trend_slug=slug,
                direction=direction,
                delta=delta,
                old_score=existing.relevance_score,
                new_score=new_entry.relevance_score,
            )
        return None
