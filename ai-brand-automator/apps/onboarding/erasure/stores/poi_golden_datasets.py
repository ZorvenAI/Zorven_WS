"""M-02 · POI golden-dataset store.

Calls POI's DELETE /v1/admin/erasure endpoint to soft-delete golden
dataset candidates linked to the erased sessions.
"""

from __future__ import annotations

import logging

import requests
from decouple import config

from apps.onboarding.erasure.registry import (
    ErasureManifest,
    ErasureStore,
    StoreRegistry,
    StoreResult,
)

logger = logging.getLogger(__name__)

TIMEOUT_S = 10

POI_SERVICE_URL = config(
    "POI_SERVICE_URL", default="http://prompt-optimization-svc:8110"
)
POI_SERVICE_TOKEN = config("POI_SERVICE_TOKEN", default="dev-service-token")


@StoreRegistry.register
class POIGoldenStore(ErasureStore):
    store_name = "poi_golden"
    artifact_types = ("golden_candidates",)

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

        url = f"{POI_SERVICE_URL}/v1/admin/erasure"
        try:
            resp = requests.delete(
                url,
                json={
                    "tenant_id": tenant_id,
                    "session_ids": [str(s) for s in session_ids],
                },
                headers={"X-Service-Token": POI_SERVICE_TOKEN},
                timeout=TIMEOUT_S,
            )
            resp.raise_for_status()
            data = resp.json()
            caveats = data.get("caveats", [])
            return StoreResult(
                store_name=self.store_name,
                items_erased=data.get("deactivated", 0),
                caveats=[c.get("reason", "") for c in caveats],
                details={"caveats": caveats},
            )
        except Exception as exc:
            logger.warning("erasure_poi_golden_failed", extra={"error": str(exc)})
            return StoreResult(
                store_name=self.store_name,
                errors=[str(exc)],
            )
