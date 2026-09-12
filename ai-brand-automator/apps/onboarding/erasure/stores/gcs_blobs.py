"""M-02 · GCS blob store.

Collects GCS paths from MeetingRecording and BrandAsset, then deletes
blobs. Runs *before* the Django session store so FK relationships are
still intact for path collection.
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
class GCSBlobStore(ErasureStore):
    store_name = "gcs_storage"
    artifact_types = ("recordings", "transcripts", "captured_media")

    def collect(self, tenant_id, session_ids, subject_name):
        from apps.onboarding.models import MeetingRecording
        from onboarding.models import BrandAsset

        paths: list[dict[str, str]] = []

        recordings = MeetingRecording.objects.filter(
            tenant_id=tenant_id, session_id__in=session_ids
        )
        for rec in recordings.only("upload_gcs_path", "transcript_gcs_path"):
            if rec.upload_gcs_path:
                paths.append({"path": rec.upload_gcs_path, "bucket": ""})
            if rec.transcript_gcs_path:
                paths.append({"path": rec.transcript_gcs_path, "bucket": ""})

        assets = BrandAsset.objects.filter(
            tenant_id=tenant_id, onboarding_session_id__in=session_ids
        )
        for asset in assets.only("gcs_path", "gcs_bucket"):
            if asset.gcs_path:
                paths.append({"path": asset.gcs_path, "bucket": asset.gcs_bucket})

        return ErasureManifest(
            store_name=self.store_name,
            item_count=len(paths),
            details={"gcs_paths": paths},
        )

    def erase(self, manifest):
        from files.services import gcs_service

        paths = manifest.details.get("gcs_paths", [])
        if not paths:
            return StoreResult(store_name=self.store_name)

        erased = 0
        errors: list[str] = []
        for entry in paths:
            path = entry["path"]
            bucket = entry.get("bucket") or None
            try:
                gcs_service.delete_file(path, bucket_name=bucket)
                erased += 1
            except Exception as exc:
                errors.append(f"{path}: {exc}")
                logger.warning(
                    "erasure_gcs_blob_failed", extra={"path": path, "error": str(exc)}
                )

        return StoreResult(
            store_name=self.store_name,
            items_erased=erased,
            errors=errors,
        )
