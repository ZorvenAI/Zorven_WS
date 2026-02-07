"""
Management command to fix stale gcs_path values on BrandAsset records.

After the ingestion pipeline moves files from _landing/ to {tenant}/raw/,
the gcs_path in the DB should be updated. This command finds assets whose
gcs_path still points to _landing/ and corrects it by scanning for the
actual file location in GCS.

Usage:
    python manage.py fix_stale_gcs_paths          # Dry run (default)
    python manage.py fix_stale_gcs_paths --apply   # Apply fixes
"""

import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Fix BrandAsset records whose gcs_path still points to _landing/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply fixes (default is dry run)",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        from onboarding.models import BrandAsset
        from files.services import gcs_service

        if not gcs_service.bucket:
            self.stderr.write(self.style.ERROR("GCS not configured"))
            return

        stale_assets = BrandAsset.objects.filter(gcs_path__startswith="_landing/")
        self.stdout.write(
            f"Found {stale_assets.count()} assets with _landing/ gcs_path"
        )

        fixed = 0
        not_found = 0

        for asset in stale_assets:
            old_path = asset.gcs_path
            # Extract the filename (everything after the last /)
            filename = old_path.rsplit("/", 1)[-1]

            # Search for the file in the raw/ zone
            prefix = f"{asset.tenant_id}/raw/" if asset.tenant_id else "1/raw/"
            blobs = list(
                gcs_service.client.list_blobs(
                    gcs_service.bucket_name,
                    prefix=prefix,
                    max_results=500,
                )
            )
            matching = [b for b in blobs if b.name.endswith(filename)]

            if matching:
                new_path = matching[0].name
                self.stdout.write(f"  Asset {asset.id}: {old_path} -> {new_path}")
                if apply:
                    asset.gcs_path = new_path
                    asset.save(update_fields=["gcs_path"])
                    self.stdout.write(self.style.SUCCESS(f"    Fixed!"))
                fixed += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Asset {asset.id}: {old_path} - file NOT found in raw/"
                    )
                )
                not_found += 1

        mode = "Fixed" if apply else "Would fix"
        self.stdout.write(
            self.style.SUCCESS(f"\n{mode} {fixed} assets, {not_found} not found in GCS")
        )
        if not apply and fixed > 0:
            self.stdout.write("Run with --apply to apply fixes")
