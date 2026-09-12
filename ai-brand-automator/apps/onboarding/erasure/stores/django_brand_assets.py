"""M-02 · BrandAsset store.

BrandAsset.onboarding_session is SET_NULL, so session deletion does
not remove assets. This store queries by session FK *before* session
deletion nullifies it, then deletes explicitly.
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
class DjangoBrandAssetStore(ErasureStore):
    store_name = "brand_assets"
    artifact_types = ("captured_media",)

    def collect(self, tenant_id, session_ids, subject_name):
        from onboarding.models import BrandAsset

        assets = BrandAsset.objects.filter(
            tenant_id=tenant_id, onboarding_session_id__in=session_ids
        )
        pks = list(assets.values_list("pk", flat=True))
        return ErasureManifest(
            store_name=self.store_name,
            item_count=len(pks),
            details={"asset_pks": pks},
        )

    def erase(self, manifest):
        from onboarding.models import BrandAsset

        pks = manifest.details.get("asset_pks", [])
        if not pks:
            return StoreResult(store_name=self.store_name)

        deleted_count, _ = BrandAsset.objects.filter(pk__in=pks).delete()
        logger.info("erasure_brand_assets", extra={"deleted": deleted_count})
        return StoreResult(store_name=self.store_name, items_erased=deleted_count)
