#!/usr/bin/env python
"""
Provision GCS buckets for existing tenants.

Tenants created before per-tenant buckets were introduced will have
empty ``gcs_raw_bucket`` and ``gcs_curated_bucket`` fields.  This
script finds every such tenant and provisions the corresponding GCS
buckets using ``TenantGCSService``.

Usage:
    cd ai-brand-automator
    python scripts/provision_tenant_buckets.py          # dry-run (default)
    python scripts/provision_tenant_buckets.py --apply  # actually provision
"""

import os
import sys
import django

# ── Django bootstrap ────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

# ── Imports after Django is ready ───────────────────────────────────
from tenants.models import Tenant  # noqa: E402
from tenants.services import TenantGCSService  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Provision GCS buckets for existing tenants.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create buckets and update DB (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    # Find tenants missing bucket configuration
    tenants = Tenant.objects.filter(
        gcs_raw_bucket="",
        gcs_curated_bucket="",
    ).exclude(slug="")

    total = tenants.count()
    if total == 0:
        print("✓ All tenants already have GCS buckets configured.")
        return

    print(
        f"Found {total} tenant(s) without GCS buckets"
        f" ({'DRY RUN' if dry_run else 'APPLYING'}):\n"
    )

    if dry_run:
        for t in tenants:
            print(f"  [{t.id}] {t.name} (slug={t.slug})")
            print(f"       → would create: {t.slug}-raw, {t.slug}-curated")
        print(
            f"\nDry run complete. Re-run with --apply to provision {total} tenant(s)."
        )
        return

    service = TenantGCSService()
    success = 0
    errors = 0

    for t in tenants:
        try:
            print(f"  Provisioning buckets for [{t.id}] {t.name} ...", end=" ")
            service.create_tenant_buckets(t)
            print("✓")
            success += 1
        except Exception as exc:
            print(f"✗ ({exc})")
            errors += 1

    print(f"\nDone: {success} succeeded, {errors} failed out of {total}.")


if __name__ == "__main__":
    main()
