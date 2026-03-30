"""SKL-BSA-13: Persist narrative results to Redis cache + GCS."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
        results = {"persisted_to": ["redis"], "version": 1}

        # 1. Redis cache (always)
        if self._redis:
            await self._redis.set_json(
                f"bsa:{tenant_id}:parent",
                narrative_data,
                ttl=86400,
            )
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
