"""SKL-BSA-13: Persist narrative results to Redis cache + GCS."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# 7-day TTL for narrative persistence (aligned with design doc)
_DEFAULT_TTL = 7 * 24 * 3600


class StoryPersister:
    """Persist narrative results to Redis + GCS."""

    def __init__(self, gcs_client=None, redis_manager=None):
        self._gcs = gcs_client
        self._redis = redis_manager

    async def persist(
        self,
        tenant_id: str,
        job_id: str,
        narrative_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist narrative data to available backends."""
        results: dict[str, Any] = {"persisted_to": [], "version": 1}

        # 1. Redis cache (when available)
        if self._redis:
            ttl = getattr(settings, "STORY_PERSIST_TTL", _DEFAULT_TTL)
            await self._redis.set_json(
                f"bsa:{tenant_id}:parent",
                narrative_data,
                ttl=ttl,
            )
            results["persisted_to"].append("redis")
            logger.info("Narrative persisted to Redis for tenant %s", tenant_id)

        # 2. GCS upload (when configured)
        if self._gcs:
            gcs_uri = await self._gcs.upload_narrative(
                tenant_id, job_id, narrative_data
            )
            if gcs_uri:
                results["persisted_to"].append("gcs")
                results["gcs_uri"] = gcs_uri
                logger.info("Narrative persisted to GCS: %s", gcs_uri)

        return results
