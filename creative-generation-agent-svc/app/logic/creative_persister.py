"""SKL-CGA-13: Creative Persister.

Persists creative package to Redis (registry key) and GCS (package JSON).
Returns the GCS URI for downstream consumption.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 7-day TTL for creative persistence
_DEFAULT_TTL = 7 * 24 * 3600


class CreativePersister:
    """Persist creative package results to Redis + GCS."""

    async def persist(
        self,
        result: dict[str, Any],
        redis_manager: Any,
        gcs_client: Any,
        tenant_id: str,
        job_id: str,
    ) -> str:
        """Persist creative package to Redis and GCS.

        Args:
            result: Complete CampaignCreativePackage dict.
            redis_manager: RedisManager instance (or None).
            gcs_client: GCSClient instance (or None).
            tenant_id: Tenant identifier.
            job_id: Job identifier.

        Returns:
            GCS URI string (empty if GCS unavailable).
        """
        gcs_uri = ""

        # 1. Redis cache (when available)
        if redis_manager:
            try:
                cache_key = f"cga:{tenant_id}:{job_id}:package"
                await redis_manager.set_json(
                    cache_key,
                    result,
                    ttl=_DEFAULT_TTL,
                )

                # Update registry key for downstream agents
                registry_key = f"cga:{tenant_id}:latest"
                await redis_manager.set_json(
                    registry_key,
                    {
                        "job_id": job_id,
                        "campaign_id": result.get("campaign_id", ""),
                        "total_images": result.get("total_images_generated", 0),
                        "confidence_score": result.get("confidence_score", 0.0),
                    },
                    ttl=_DEFAULT_TTL,
                )

                logger.info(
                    "Creative package persisted to Redis for tenant %s, " "job %s",
                    tenant_id,
                    job_id,
                )
            except Exception as exc:
                logger.warning("Redis persist failed (fail-open): %s", exc)

        # 2. GCS upload (when configured)
        if gcs_client:
            try:
                gcs_uri = await gcs_client.upload_package(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    package_data=result,
                )
                if gcs_uri:
                    logger.info("Creative package persisted to GCS: %s", gcs_uri)
                else:
                    logger.warning("GCS upload returned empty URI for job %s", job_id)
            except Exception as exc:
                logger.warning("GCS persist failed (fail-open): %s", exc)

        return gcs_uri
