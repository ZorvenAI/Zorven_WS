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
        for rec in recordings.only(
            "upload_gcs_path", "transcript_gcs_path", "stream_assets"
        ):
            if rec.upload_gcs_path:
                paths.append({"path": rec.upload_gcs_path, "bucket": ""})
            if rec.transcript_gcs_path:
                paths.append({"path": rec.transcript_gcs_path, "bucket": ""})
            # O-07: a per-mic object that was never finalised has no BrandAsset
            # for the sweep below to find, so this column is the only way to
            # reach it. An erasure that reported success while leaving a
            # participant's audio in the bucket is the failure M-02 exists to
            # prevent.
            for entry in rec.stream_assets or []:
                path = entry.get("gcs_path")
                if path:
                    paths.append({"path": path, "bucket": ""})

        assets = BrandAsset.objects.filter(
            tenant_id=tenant_id, onboarding_session_id__in=session_ids
        )
        for asset in assets.only("gcs_path", "gcs_bucket"):
            if asset.gcs_path:
                paths.append({"path": asset.gcs_path, "bucket": asset.gcs_bucket})

        # One entry per object. A finalised stream is reachable from both loops
        # above, and `erase` treats a second delete of the same path as a
        # failure — GCS reports the object already gone — which would put the
        # whole erasure's `completeness_verified` at False and overstate
        # `item_count`. The BrandAsset copy wins where both exist: it carries
        # the real bucket, while `stream_assets` has no bucket to record.
        by_path: dict[str, dict[str, str]] = {}
        for entry in paths:
            seen = by_path.get(entry["path"])
            if seen is None or (not seen["bucket"] and entry["bucket"]):
                by_path[entry["path"]] = entry
        paths = list(by_path.values())

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
