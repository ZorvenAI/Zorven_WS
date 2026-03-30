"""SKL-CAA-11: Blueprint Persister.

Persists campaign blueprint to Redis cache + GCS for downstream
agents (3.2 Creative, 3.3 Ad Copy, 3.4 Publisher, 3.5 Monitor).
"""

import logging
from typing import Any

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.services.gcs_client import GCSClient

logger = logging.getLogger(__name__)


class BlueprintPersister:
    """Persist blueprint results to Redis + GCS."""

    def __init__(
        self,
        redis_manager: RedisManager | None = None,
        gcs_client: GCSClient | None = None,
    ):
        self._redis = redis_manager
        self._gcs = gcs_client

    async def persist(
        self,
        tenant_id: str,
        job_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist blueprint to Redis + GCS.

        Returns dict with persisted_to list and gcs_uri.
        """
        persisted_to: list[str] = []
        gcs_uri = ""

        # Redis
        if self._redis:
            try:
                await self._redis.save_blueprint(tenant_id, result)
                persisted_to.append("redis")
            except Exception as exc:
                logger.warning("Blueprint Redis persist failed: %s", exc)

        # GCS
        if self._gcs:
            try:
                uri = await self._gcs.upload_blueprint(tenant_id, job_id, result)
                if uri:
                    gcs_uri = uri
                    persisted_to.append("gcs")
            except Exception as exc:
                logger.warning("Blueprint GCS persist failed: %s", exc)

        return {
            "persisted_to": persisted_to,
            "gcs_uri": gcs_uri,
        }
