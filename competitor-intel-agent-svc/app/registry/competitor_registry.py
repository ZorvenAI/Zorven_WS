"""
Competitor Registry — Redis Hash CRUD + snapshot management.

Maintains a persistent registry of known competitors per tenant.
Redis keys:
  cia:{tenant_id}:registry:competitors — Hash of slug -> JSON profile
  cia:{tenant_id}:registry:snapshots:{slug} — Sorted set of date -> snapshot JSON
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_SNAPSHOT_TTL = 90 * 24 * 60 * 60  # 90 days


class CompetitorRegistry:
    """Persistent competitor registry backed by Redis Hash."""

    def __init__(self, redis_client: Optional[aioredis.Redis] = None) -> None:
        self._redis = redis_client

    def _registry_key(self, tenant_id: str) -> str:
        return f"cia:{tenant_id}:registry:competitors"

    def _snapshot_key(self, tenant_id: str, slug: str) -> str:
        return f"cia:{tenant_id}:registry:snapshots:{slug}"

    async def get_competitor(
        self, tenant_id: str, slug: str
    ) -> Optional[dict[str, Any]]:
        """Get a single competitor profile from the registry."""
        if not self._redis:
            return None
        try:
            data = await self._redis.hget(self._registry_key(tenant_id), slug)
            if data:
                return json.loads(data)
            return None
        except Exception as exc:
            logger.warning("Registry get failed: %s", exc)
            return None

    async def set_competitor(
        self, tenant_id: str, slug: str, profile: dict[str, Any]
    ) -> None:
        """Set a competitor profile in the registry."""
        if not self._redis:
            return
        try:
            profile["last_updated"] = datetime.now(timezone.utc).isoformat()
            await self._redis.hset(
                self._registry_key(tenant_id), slug, json.dumps(profile)
            )
        except Exception as exc:
            logger.warning("Registry set failed: %s", exc)

    async def get_all_competitors(
        self, tenant_id: str
    ) -> dict[str, dict[str, Any]]:
        """Get all competitors for a tenant."""
        if not self._redis:
            return {}
        try:
            raw = await self._redis.hgetall(self._registry_key(tenant_id))
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning("Registry getall failed: %s", exc)
            return {}

    async def delete_competitor(self, tenant_id: str, slug: str) -> bool:
        """Remove a competitor from the registry."""
        if not self._redis:
            return False
        try:
            result = await self._redis.hdel(self._registry_key(tenant_id), slug)
            return result > 0
        except Exception as exc:
            logger.warning("Registry delete failed: %s", exc)
            return False

    async def competitor_count(self, tenant_id: str) -> int:
        """Count competitors in the registry."""
        if not self._redis:
            return 0
        try:
            return await self._redis.hlen(self._registry_key(tenant_id))
        except Exception as exc:
            logger.warning("Registry count failed: %s", exc)
            return 0

    async def create_snapshot(
        self, tenant_id: str, slug: str, profile: dict[str, Any]
    ) -> None:
        """Create a timestamped snapshot for change detection."""
        if not self._redis:
            return
        try:
            key = self._snapshot_key(tenant_id, slug)
            now = datetime.now(timezone.utc).isoformat()
            await self._redis.set(
                f"{key}:{now[:10]}", json.dumps(profile), ex=_SNAPSHOT_TTL
            )
        except Exception as exc:
            logger.warning("Snapshot creation failed: %s", exc)

    async def detect_changes(
        self,
        tenant_id: str,
        slug: str,
        current_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare current profile against the stored registry entry.

        Returns a dict with changed fields, or empty dict if no changes.
        """
        stored = await self.get_competitor(tenant_id, slug)
        if not stored:
            return {"status": "new", "slug": slug}

        changes: dict[str, Any] = {}
        compare_fields = [
            "name", "website", "market_position", "description",
        ]
        for field in compare_fields:
            old_val = stored.get(field, "")
            new_val = current_profile.get(field, "")
            if old_val != new_val and new_val:
                changes[field] = {"old": old_val, "new": new_val}

        if changes:
            return {"status": "changed", "slug": slug, "changes": changes}
        return {}
