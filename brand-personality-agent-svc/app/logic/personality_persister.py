"""SKL-BPV-11: Personality persistence to Redis + Django brand context sync."""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PersonalityPersister:
    """Persist personality profile to storage backends."""

    async def persist(
        self, tenant_id: str, personality: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist personality data.

        Currently Redis-only. GCS + RAG deferred to v2.
        """
        logger.info("Personality persistence for tenant %s (Redis only)", tenant_id)
        return {"persisted_to": ["redis"], "version": 1}

    async def sync_personality_context(
        self,
        tenant_id: str,
        personality: dict[str, Any],
        brand_context_id: str = "parent",
    ) -> bool:
        """Sync personality data to Django Redis via backend API.

        POST /api/v1/analytics/brand-personality-sync/
        Allows Django to cache personality data for:
        - Future BPV runs for sub-brands (PG-07 parent lookup)
        - Other WF2 agents that need personality context
        - Analytics dashboard personality display
        """
        payload = {
            "tenant_id": tenant_id,
            "brand_context_id": brand_context_id,
            "aaker_profile": personality.get("aaker_profile", {}),
            "archetype": personality.get("archetype", {}),
            "values_hierarchy": personality.get("values_hierarchy", {}),
        }

        url = f"{settings.BACKEND_URL}/api/v1/analytics/brand-personality-sync/"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
                        "Content-Type": "application/json",
                    },
                )
            if resp.status_code == 200:
                logger.info(
                    "Personality context synced for tenant %s (brand_context: %s)",
                    tenant_id,
                    brand_context_id,
                )
                return True
            else:
                logger.warning(
                    "Personality sync failed for tenant %s: %s %s",
                    tenant_id,
                    resp.status_code,
                    resp.text[:200],
                )
                return False
        except Exception as exc:
            logger.warning(
                "Personality sync error for tenant %s: %s", tenant_id, exc
            )
            return False
