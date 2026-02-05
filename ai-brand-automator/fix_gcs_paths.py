#!/usr/bin/env python
"""
Script to fix GCS paths in BrandAsset table.
The files were moved from _landing/ to 1/raw/... during ingestion
but the database wasn't updated.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from onboarding.models import BrandAsset  # noqa: E402
from files.services import gcs_service  # noqa: E402


def fix_gcs_paths():
    if not gcs_service.bucket:
        print("GCS not configured!")
        return

    # List all actual files in GCS
    blobs = list(gcs_service.bucket.list_blobs(prefix="1/"))
    gcs_files = [b.name for b in blobs]
    print(f"Found {len(gcs_files)} files in GCS")

    # Get all assets
    updated = 0
    not_found = 0

    for asset in BrandAsset.objects.all():
        if not asset.gcs_path:
            continue

        # Check if current path exists
        blob = gcs_service.bucket.blob(asset.gcs_path)
        if blob.exists():
            print(f"Asset {asset.id}: OK - {asset.gcs_path}")
            continue

        # Extract the filename with UUID prefix
        old_path = asset.gcs_path
        filename_with_uuid = old_path.split("/")[-1]

        # Find matching file in GCS
        matched = None
        for gcs_path in gcs_files:
            if filename_with_uuid in gcs_path:
                matched = gcs_path
                break

        if matched:
            print(f"Asset {asset.id}: UPDATING {old_path} -> {matched}")
            asset.gcs_path = matched
            asset.save()
            updated += 1
        else:
            print(f"Asset {asset.id}: NO MATCH for {old_path}")
            not_found += 1

    print(f"\nDone! Updated: {updated}, Not found: {not_found}")


if __name__ == "__main__":
    fix_gcs_paths()
