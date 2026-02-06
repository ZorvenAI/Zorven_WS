#!/usr/bin/env python
"""Fix GCS paths for assets with wrong _landing prefix."""
import django
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from files.services import GCSService  # noqa: E402
from onboarding.models import BrandAsset  # noqa: E402

gcs = GCSService()

# Get all blobs from GCS
blobs = list(gcs.bucket.list_blobs(prefix="1/raw/2026/02/"))
blob_map = {}
for b in blobs:
    # Extract UUID prefix (first 8 chars after last /)
    filename = b.name.split("/")[-1]
    uuid_prefix = filename.split("_")[0]
    blob_map[uuid_prefix] = b.name

print(f"Found {len(blob_map)} files in GCS")

# Get assets with wrong _landing paths
assets = BrandAsset.objects.filter(gcs_path__startswith="_landing/")
print(f"Found {assets.count()} assets with _landing paths to fix")

fixed = 0
for asset in assets:
    old_path = asset.gcs_path
    filename = old_path.split("/")[-1]
    uuid_prefix = filename.split("_")[0]

    if uuid_prefix in blob_map:
        new_path = blob_map[uuid_prefix]
        asset.gcs_path = new_path
        asset.save()
        print(f"Fixed asset {asset.id}: {old_path} -> {new_path}")
        fixed += 1
    else:
        print(f"No match for asset {asset.id}: {old_path} (prefix: {uuid_prefix})")

print(f"\nFixed {fixed} assets")
