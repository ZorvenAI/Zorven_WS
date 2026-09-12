"""M-02 · OIA Redis store.

Calls OIA's DELETE /v1/admin/erasure endpoint to clean all
session-scoped Redis keys.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from apps.onboarding.erasure.registry import (
    ErasureManifest,
    ErasureStore,
    StoreRegistry,
    StoreResult,
)

logger = logging.getLogger(__name__)

TIMEOUT_S = 10


@StoreRegistry.register
class OIARedisStore(ErasureStore):
    store_name = "oia_redis"
    artifact_types = ("transcripts", "summaries")

    def collect(self, tenant_id, session_ids, subject_name):
        return ErasureManifest(
            store_name=self.store_name,
            item_count=len(session_ids),
            details={
                "tenant_id": tenant_id,
                "session_ids": session_ids,
            },
        )

    def erase(self, manifest):
        tenant_id = manifest.details.get("tenant_id", "")
        session_ids = manifest.details.get("session_ids", [])
        if not session_ids:
            return StoreResult(store_name=self.store_name)

        url = f"{settings.OIA_SERVICE_URL}/v1/admin/erasure"
        try:
            resp = requests.delete(
                url,
                json={
                    "tenant_id": tenant_id,
                    "session_ids": [str(s) for s in session_ids],
                },
                headers={"X-Service-Token": settings.OIA_SERVICE_TOKEN},
                timeout=TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            return StoreResult(
                store_name=self.store_name,
                items_erased=data.get("total", 0),
                details={"deleted_keys": data.get("deleted_keys", [])},
            )
        except Exception as exc:
            logger.warning("erasure_oia_redis_failed", extra={"error": str(exc)})
            return StoreResult(
                store_name=self.store_name,
                errors=[str(exc)],
            )
