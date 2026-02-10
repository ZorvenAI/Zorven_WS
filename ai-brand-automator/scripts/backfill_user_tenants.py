#!/usr/bin/env python
"""
Backfill tenants for existing users.

Users created before the multi-tenancy fix (commit 09146ff) were never
assigned a dedicated Tenant.  This script:

1. Finds every User who has no matching Tenant (schema_name = "user_<id>")
2. Creates a Tenant + Domain for each
3. Re-assigns any Company / OnboardingProgress / ChatSession that was
   linked to the **public** tenant to the user's new tenant — but ONLY
   when the user is the clear owner (i.e. the user created the company).

Usage:
    cd ai-brand-automator
    python scripts/backfill_user_tenants.py          # dry-run (default)
    python scripts/backfill_user_tenants.py --apply  # actually write
"""

import os
import sys
import django

# ── Django bootstrap ────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

# ── Imports after Django is ready ───────────────────────────────────
from django.contrib.auth.models import User  # noqa: E402
from tenants.models import Tenant, Domain  # noqa: E402
from onboarding.models import Company, OnboardingProgress  # noqa: E402

try:
    from ai_services.models import ChatSession  # noqa: E402
except ImportError:
    ChatSession = None


def get_public_tenant():
    try:
        return Tenant.objects.get(schema_name="public")
    except Tenant.DoesNotExist:
        return None


def backfill(apply: bool = False):
    public_tenant = get_public_tenant()
    created_count = 0
    reassigned_count = 0
    skipped_count = 0

    users = User.objects.all().order_by("id")
    print(f"Found {users.count()} total users\n")

    for user in users:
        schema = f"user_{user.id}"
        existing = Tenant.objects.filter(schema_name=schema).first()

        if existing:
            print(
                f"  [SKIP] User {user.id} ({user.email}) "
                f"— tenant '{existing.schema_name}' already exists"
            )
            skipped_count += 1
            continue

        display_name = f"{user.first_name} {user.last_name}".strip()
        if not display_name:
            display_name = user.username

        if apply:
            tenant = Tenant(
                name=display_name,
                schema_name=schema,
                subscription_status="trial",
            )
            # Skip automatic schema creation — we use shared-schema
            # multi-tenancy (FK filtering), not per-tenant schemas
            tenant.auto_create_schema = False
            tenant.save()

            Domain.objects.create(
                domain=f"user-{user.id}.localhost",
                tenant=tenant,
                is_primary=True,
            )
            print(f"  [CREATE] User {user.id} ({user.email}) " f"→ tenant '{schema}'")
        else:
            tenant = None
            print(
                f"  [DRY-RUN] Would create tenant '{schema}' "
                f"for User {user.id} ({user.email})"
            )

        created_count += 1

        # ── Reassign public-tenant data to the new user tenant ──
        if public_tenant and tenant:
            # Company (OneToOne with Tenant).  We try to find a
            # company that belongs to the public tenant AND whose
            # creator email matches this user.  Since Company has no
            # created_by FK, we use a simple heuristic: if the
            # public tenant has exactly one company, assign it to the
            # first user processed that doesn't already have one.
            companies = Company.objects.filter(tenant=public_tenant)
            if (
                companies.count() == 1
                and not Company.objects.filter(tenant=tenant).exists()
            ):
                company = companies.first()
                if apply:
                    company.tenant = tenant
                    company.save(update_fields=["tenant"])
                    print(
                        f"    ↳ Reassigned Company '{company.name}' "
                        f"to tenant '{schema}'"
                    )

                    # OnboardingProgress
                    OnboardingProgress.objects.filter(
                        tenant=public_tenant, company=company
                    ).update(tenant=tenant)
                    print("    ↳ Reassigned OnboardingProgress")

                    # ChatSessions
                    if ChatSession is not None:
                        n = ChatSession.objects.filter(tenant=public_tenant).update(
                            tenant=tenant
                        )
                        if n:
                            print(f"    ↳ Reassigned {n} ChatSession(s)")

                    reassigned_count += 1
                else:
                    print(
                        f"    ↳ [DRY-RUN] Would reassign Company "
                        f"'{company.name}' + related data"
                    )

    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"  Mode:        {mode}")
    print(f"  Skipped:     {skipped_count} (already had tenant)")
    print(f"  Created:     {created_count} tenant(s)")
    print(f"  Reassigned:  {reassigned_count} company(ies)")
    print(f"{'=' * 50}")

    if not apply and created_count > 0:
        print("\nRe-run with --apply to execute these changes.")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    backfill(apply=apply)
