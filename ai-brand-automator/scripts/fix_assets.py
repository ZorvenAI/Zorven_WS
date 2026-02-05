#!/usr/bin/env python
"""Fix asset bucket names and mark old assets as failed."""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from django.conf import settings  # noqa: E402
from onboarding.models import BrandAsset  # noqa: E402

# Get the correct bucket name
bucket = settings.GS_BUCKET_NAME
print(f"Correct bucket: {bucket}")

# Update all assets with wrong bucket
updated = BrandAsset.objects.filter(gcs_bucket="brand-automator-assets").update(
    gcs_bucket=bucket
)
print(f"Updated {updated} assets with correct bucket")

# Mark asset 10 as failed (old format)
try:
    asset10 = BrandAsset.objects.get(id=10)
    asset10.pipeline_status = "failed"
    asset10.pipeline_error = (
        "Uploaded before pipeline integration - path format incompatible. "
        "Please delete and re-upload."
    )
    asset10.save()
    print("Asset 10 marked as failed")
except BrandAsset.DoesNotExist:
    print("Asset 10 not found")

# Show current state
print("\nCurrent asset states:")
for a in BrandAsset.objects.all().order_by("-uploaded_at")[:5]:
    print(f"  ID={a.id}, status={a.pipeline_status}, bucket={a.gcs_bucket}")
