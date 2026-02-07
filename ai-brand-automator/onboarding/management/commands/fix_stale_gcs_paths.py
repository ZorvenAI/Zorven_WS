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

        # Resolve public tenant ID dynamically for fallback
        from tenants.models import Tenant

        try:
            public_tenant = Tenant.objects.get(schema_name="public")
            public_tenant_id = public_tenant.id
        except Tenant.DoesNotExist:
            public_tenant_id = 1
            self.stdout.write(
                self.style.WARNING(
                    "Public tenant not found, "
                    f"using fallback tenant_id={public_tenant_id}"
                )
            )

        stale_assets = BrandAsset.objects.filter(gcs_path__startswith="_landing/")
        self.stdout.write(
            f"Found {stale_assets.count()} assets with _landing/ gcs_path"
        )

        fixed = 0
        not_found = 0
        skipped = 0

        for asset in stale_assets:
            old_path = asset.gcs_path
            # Extract the filename (everything after the last /)
            filename = old_path.rsplit("/", 1)[-1]

            # Build a narrowed prefix using tenant_id and uploaded_at date
            tenant_id = asset.tenant_id if asset.tenant_id else public_tenant_id
            if asset.uploaded_at:
                date_prefix = asset.uploaded_at.strftime("%Y/%m/%d")
                prefix = f"{tenant_id}/raw/{date_prefix}/"
            else:
                prefix = f"{tenant_id}/raw/"

            # Stream blobs and stop at first match (no max_results limit)
            matching_blob = None
            match_count = 0
            for blob in gcs_service.client.list_blobs(
                gcs_service.bucket_name,
                prefix=prefix,
            ):
                if blob.name.endswith(filename):
                    match_count += 1
                    if matching_blob is None:
                        matching_blob = blob
                    if match_count > 1:
                        break  # Found ambiguity, stop early

            if match_count > 1:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Asset {asset.id}: {old_path} - SKIPPED: "
                        f"multiple files match '{filename}' in {prefix}"
                    )
                )
                skipped += 1
            elif matching_blob:
                new_path = matching_blob.name
                self.stdout.write(f"  Asset {asset.id}: {old_path} -> {new_path}")
                if apply:
                    asset.gcs_path = new_path
                    asset.save(update_fields=["gcs_path"])
                    self.stdout.write(self.style.SUCCESS("    Fixed!"))
                fixed += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Asset {asset.id}: {old_path} - file NOT found in {prefix}"
                    )
                )
                not_found += 1

        mode = "Fixed" if apply else "Would fix"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode} {fixed} assets, {not_found} not found, "
                f"{skipped} skipped (ambiguous)"
            )
        )
        if not apply and fixed > 0:
            self.stdout.write("Run with --apply to apply fixes")
