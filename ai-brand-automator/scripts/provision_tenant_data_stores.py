#!/usr/bin/env python
"""
Provision Vertex AI data stores for existing tenants.

Tenants created before per-tenant data stores were introduced will have
an empty ``vertex_ai_data_store_id`` field.  This script finds every
such tenant and provisions the corresponding Vertex AI data store using
``TenantVertexAIService``.

Usage:
    cd ai-brand-automator
    python scripts/provision_tenant_data_stores.py          # dry-run (default)
    python scripts/provision_tenant_data_stores.py --apply  # actually provision
"""

import os
import sys
import django

# -- Django bootstrap --------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

# -- Imports after Django is ready -------------------------------------------
from tenants.models import Tenant  # noqa: E402
from tenants.services import TenantVertexAIService  # noqa: E402


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Provision Vertex AI data stores for existing tenants.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create data stores and update DB (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.apply

    # Find tenants missing data store configuration
    tenants = Tenant.objects.filter(
        vertex_ai_data_store_id="",
    ).exclude(slug="")

    total = tenants.count()
    if total == 0:
        print("All tenants already have Vertex AI data stores configured.")
        return

    print(
        f"Found {total} tenant(s) without Vertex AI data stores"
        f" ({'DRY RUN' if dry_run else 'APPLYING'}):\n"
    )

    if dry_run:
        for t in tenants:
            print(f"  [{t.id}] {t.name} (slug={t.slug})")
            print(f"       -> would create data store: prevision-{t.slug}")
        print(
            f"\nDry run complete. Re-run with --apply to provision {total} tenant(s)."
        )
        return

    service = TenantVertexAIService()
    success = 0
    errors = 0

    for t in tenants:
        try:
            print(f"  Provisioning data store for [{t.id}] {t.name} ...", end=" ")
            service.create_tenant_data_store(t)
            print("OK")
            success += 1
        except Exception as exc:
            print(f"FAILED ({exc})")
            errors += 1

    print(f"\nDone: {success} succeeded, {errors} failed out of {total}.")


if __name__ == "__main__":
    main()
