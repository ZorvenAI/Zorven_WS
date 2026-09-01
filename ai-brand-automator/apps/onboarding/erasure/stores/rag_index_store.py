"""M-02 · RAG index store.

OIA session models are not directly synced to Vertex AI — only Company
is. After session data and provenance are erased, this store triggers a
Company document re-sync so the RAG index reflects the removal.
"""

from __future__ import annotations

import logging

from apps.onboarding.erasure.registry import (
    ErasureManifest,
    ErasureStore,
    StoreRegistry,
    StoreResult,
)

logger = logging.getLogger(__name__)


@StoreRegistry.register
class RAGIndexStore(ErasureStore):
    store_name = "rag_index"
    artifact_types = ("rag_entries",)

    def collect(self, tenant_id, session_ids, subject_name):
        from apps.onboarding.models import OnboardingSession

        company_ids = list(
            OnboardingSession.objects.filter(tenant_id=tenant_id, pk__in=session_ids)
            .values_list("company_id", flat=True)
            .distinct()
        )
        return ErasureManifest(
            store_name=self.store_name,
            item_count=len(company_ids),
            details={"company_ids": company_ids, "tenant_id": tenant_id},
        )

    def erase(self, manifest):
        company_ids = manifest.details.get("company_ids", [])
        if not company_ids:
            return StoreResult(store_name=self.store_name)

        synced = 0
        errors: list[str] = []
        for company_id in company_ids:
            try:
                from rag_index.tasks import sync_model_to_rag

                sync_model_to_rag.apply_async(
                    args=["Company", company_id, manifest.details.get("tenant_id")]
                )
                synced += 1
            except Exception as exc:
                errors.append(f"company {company_id}: {exc}")
                logger.warning(
                    "erasure_rag_resync_failed",
                    extra={"company_id": company_id, "error": str(exc)},
                )

        return StoreResult(
            store_name=self.store_name,
            items_erased=synced,
            errors=errors,
            details={"resynced_companies": company_ids},
        )
