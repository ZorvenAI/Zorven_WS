"""Persona Registry — Redis Hash CRUD + version snapshots for evolution detection.

Redis keys:
  apa:{tenant_id}:registry:personas — Hash of slug -> JSON profile
  apa:{tenant_id}:registry:version:{slug}:{ver} — Version snapshots (180d TTL)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.events.catalog import EventEmitter, EventType

logger = logging.getLogger(__name__)


class PersonaRegistry:
    """Persistent persona registry backed by Redis Hash."""

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self._redis = redis_client
        self._events = event_emitter

    def _registry_key(self, tenant_id: str) -> str:
        return f"apa:{tenant_id}:registry:personas"

    def _version_key(self, tenant_id: str, slug: str, version: int) -> str:
        return f"apa:{tenant_id}:registry:version:{slug}:{version}"

    async def get_persona(self, tenant_id: str, slug: str) -> dict[str, Any] | None:
        """Get a single persona profile from the registry."""
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

    async def get_all_personas(self, tenant_id: str) -> dict[str, dict[str, Any]]:
        """Get all personas for a tenant."""
        if not self._redis:
            return {}
        try:
            raw = await self._redis.hgetall(self._registry_key(tenant_id))
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning("Registry getall failed: %s", exc)
            return {}

    async def upsert_persona(
        self, tenant_id: str, slug: str, profile: dict[str, Any]
    ) -> None:
        """Insert or update a persona profile, with evolution detection."""
        if not self._redis:
            return
        try:
            # Check for evolution
            existing = await self.get_persona(tenant_id, slug)
            if existing:
                changes = self.detect_evolution(existing, profile)
                if changes:
                    # Emit evolution event
                    if self._events:
                        await self._events.emit(
                            EventType.PERSONA_EVOLUTION_DETECTED,
                            tenant_id=tenant_id,
                            detail={
                                "slug": slug,
                                "changes": changes,
                            },
                        )
                    old_version = existing.get("version", 1)
                    new_version = old_version + 1
                    profile["version"] = new_version
                else:
                    profile["version"] = existing.get("version", 1)
            else:
                profile["version"] = 1

            profile["last_updated"] = datetime.now(timezone.utc).isoformat()

            await self._redis.hset(
                self._registry_key(tenant_id),
                slug,
                json.dumps(profile),
            )

            # Create version snapshot
            await self._create_snapshot(tenant_id, slug, profile)

            # Emit registry update event
            if self._events:
                await self._events.emit(
                    EventType.PERSONA_REGISTRY_UPDATED,
                    tenant_id=tenant_id,
                    detail={"slug": slug, "version": profile.get("version", 1)},
                )

        except Exception as exc:
            logger.warning("Registry upsert failed: %s", exc)

    async def delete_persona(self, tenant_id: str, slug: str) -> bool:
        """Remove a persona from the registry."""
        if not self._redis:
            return False
        try:
            result = await self._redis.hdel(self._registry_key(tenant_id), slug)
            return result > 0
        except Exception as exc:
            logger.warning("Registry delete failed: %s", exc)
            return False

    async def persona_count(self, tenant_id: str) -> int:
        """Count personas in the registry."""
        if not self._redis:
            return 0
        try:
            return await self._redis.hlen(self._registry_key(tenant_id))
        except Exception as exc:
            logger.warning("Registry count failed: %s", exc)
            return 0

    @staticmethod
    def detect_evolution(
        old_profile: dict[str, Any],
        new_profile: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare profiles and return changed fields."""
        changes: dict[str, Any] = {}
        compare_fields = [
            "segment_label",
            "data_source",
            "priority_score",
            "confidence_score",
            "pain_points",
            "motivations",
            "objections",
            "preferred_channels",
        ]
        for field in compare_fields:
            old_val = old_profile.get(field)
            new_val = new_profile.get(field)
            if old_val != new_val and new_val is not None:
                changes[field] = {"old": old_val, "new": new_val}

        return changes

    async def _create_snapshot(
        self, tenant_id: str, slug: str, profile: dict[str, Any]
    ) -> None:
        """Create a versioned snapshot for historical tracking."""
        if not self._redis:
            return
        try:
            version = profile.get("version", 1)
            key = self._version_key(tenant_id, slug, version)
            await self._redis.set(
                key,
                json.dumps(profile),
                ex=settings.PERSONA_VERSION_TTL,
            )
        except Exception as exc:
            logger.warning("Snapshot creation failed: %s", exc)
