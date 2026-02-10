#!/usr/bin/env python
"""
Phase 8 — One-time migration: Convert user_{id} tenants to membership-based model.

For each Tenant with schema_name matching "user_{N}":
  1. Find User N
  2. Create Membership(user=N, tenant=T, role=OWNER)
  3. If tenant has a Company → rename tenant to company.name
  4. Regenerate schema_name as tenant_{slug}
  5. Update Domain record to {slug}.localhost

Idempotent: skips if Membership already exists.

Usage:
    cd ai-brand-automator
    python scripts/migrate_to_membership.py          # dry-run (default)
    python scripts/migrate_to_membership.py --apply  # actually write
"""

import os
import re
import sys

import django

# ── Django bootstrap ────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

# ── Imports after Django is ready ───────────────────────────────────
from django.contrib.auth.models import User  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.text import slugify  # noqa: E402

from onboarding.models import Company  # noqa: E402
from tenants.models import Domain, Membership, Tenant  # noqa: E402

# ── Counters ────────────────────────────────────────────────────────
stats = {
    "memberships_created": 0,
    "tenants_renamed": 0,
    "schemas_updated": 0,
    "domains_updated": 0,
    "skipped_has_membership": 0,
    "skipped_no_user": 0,
}


def _unique_slug(base: str, existing: set[str]) -> str:
    """Generate a slug that's unique in both DB and the running set."""
    slug = slugify(base) or "workspace"
    candidate = slug
    counter = 1
    while candidate in existing or Tenant.objects.filter(slug=candidate).exists():
        candidate = f"{slug}-{counter}"
        counter += 1
    existing.add(candidate)
    return candidate


def _unique_schema(slug: str) -> str:
    """Generate a unique schema_name from a slug."""
    schema = re.sub(r"[^a-zA-Z0-9_]", "_", slug)
    schema = f"tenant_{schema}"
    candidate = schema
    counter = 1
    while Tenant.objects.filter(schema_name=candidate).exists():
        candidate = f"{schema}_{counter}"
        counter += 1
    return candidate


def migrate(apply: bool = False):
    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print("=" * 60)

    used_slugs: set[str] = set(Tenant.objects.values_list("slug", flat=True))

    # Find all tenants that still need processing:
    #   - schema_name starts with "user_" (not yet migrated), OR
    #   - schema_name starts with "tenant_" but has no Membership (interrupted run)
    user_tenants = []
    for t in Tenant.objects.all().order_by("id"):
        if t.schema_name == "public":
            continue
        if t.schema_name.startswith("user_"):
            try:
                uid = int(t.schema_name.split("_", 1)[1])
                user_tenants.append((uid, t))
            except (ValueError, IndexError):
                pass
        elif t.schema_name.startswith("tenant_"):
            # Check if this was a partially-migrated tenant
            # (has membership but domain may still be old)
            membership = Membership.objects.filter(tenant=t).first()
            if membership and membership.user_id:
                # Check if domain still uses old user-{N} format
                old_style_domain = Domain.objects.filter(
                    tenant=t, domain__startswith="user-"
                ).first()
                if old_style_domain:
                    user_tenants.append((membership.user_id, t))

    print(f"Found {len(user_tenants)} tenant(s) to process\n")

    for uid, tenant in user_tenants:
        print(f"  T#{tenant.id} schema={tenant.schema_name}")

        # ── Step 1: Find the user ───────────────────────────────
        try:
            user = User.objects.get(id=uid)
        except User.DoesNotExist:
            print(f"    [SKIP] No User with id={uid}")
            stats["skipped_no_user"] += 1
            continue

        # ── Step 2: Create Membership (OWNER) ───────────────────
        existing_membership = Membership.objects.filter(
            user=user, tenant=tenant
        ).first()
        if existing_membership:
            print(
                f"    [SKIP] Membership already exists "
                f"(role={existing_membership.role})"
            )
            stats["skipped_has_membership"] += 1
            # Still proceed with rename/schema steps below
        else:
            if apply:
                Membership.objects.create(
                    user=user,
                    tenant=tenant,
                    role=Membership.Role.OWNER,
                    is_active=True,
                    accepted_at=timezone.now(),
                )
            print(
                f"    {'[CREATE]' if apply else '[DRY-RUN]'} "
                f"Membership: {user.email} → {tenant.name} (OWNER)"
            )
            stats["memberships_created"] += 1

        # ── Step 3: Rename tenant if a Company is linked ────────
        try:
            company = Company.objects.get(tenant=tenant)
            new_name = company.name
        except Company.DoesNotExist:
            company = None
            new_name = None

        if new_name and new_name != tenant.name:
            if apply:
                tenant.name = new_name
                # Will save below after schema update
            print(f"    {'[RENAME]' if apply else '[DRY-RUN]'} " f"→ name='{new_name}'")
            stats["tenants_renamed"] += 1

        # ── Step 4: Update slug + schema_name ───────────────────
        # Determine best base for slugification
        slug_base = new_name or tenant.name
        old_schema = tenant.schema_name
        needs_schema_update = old_schema.startswith("user_")

        if needs_schema_update:
            new_slug = _unique_slug(slug_base, used_slugs)
            new_schema = _unique_schema(new_slug)

            if apply:
                tenant.slug = new_slug
                tenant.schema_name = new_schema
                # CRITICAL: prevent django-tenants from creating a
                # PostgreSQL schema — we use shared-schema FK filtering
                tenant.auto_create_schema = False
                tenant.save(update_fields=["name", "slug", "schema_name"])
            print(
                f"    {'[UPDATE]' if apply else '[DRY-RUN]'} "
                f"slug='{new_slug}', schema='{new_schema}'"
            )
            stats["schemas_updated"] += 1
        else:
            # Schema already updated (interrupted run), reuse its slug
            new_slug = tenant.slug

        # ── Step 5: Update Domain ───────────────────────────────
        # Look for any old-style user-N domain OR mismatched domain
        old_domain_pattern = f"user-{uid}.localhost"
        domain_obj = Domain.objects.filter(
            tenant=tenant, domain=old_domain_pattern
        ).first()
        if not domain_obj:
            # Also check for any domain that doesn't match the new slug
            domain_obj = Domain.objects.filter(
                tenant=tenant, domain__startswith="user-"
            ).first()
        new_domain = f"{new_slug}.localhost"
        if domain_obj and domain_obj.domain != new_domain:
            old_domain_val = domain_obj.domain
            if apply:
                domain_obj.domain = new_domain
                domain_obj.save(update_fields=["domain"])
            print(
                f"    {'[DOMAIN]' if apply else '[DRY-RUN]'} "
                f"'{old_domain_val}' → '{new_domain}'"
            )
            stats["domains_updated"] += 1
        elif not domain_obj:
            print("    [NOTE] No old-style domain found, skipping")

        print()

    # ── Summary ─────────────────────────────────────────────────
    print("=" * 60)
    print(f"  Mode:                 {'APPLIED' if apply else 'DRY-RUN'}")
    print(f"  Memberships created:  {stats['memberships_created']}")
    print(f"  Tenants renamed:      {stats['tenants_renamed']}")
    print(f"  Schemas updated:      {stats['schemas_updated']}")
    print(f"  Domains updated:      {stats['domains_updated']}")
    print(f"  Skipped (membership): {stats['skipped_has_membership']}")
    print(f"  Skipped (no user):    {stats['skipped_no_user']}")
    print("=" * 60)

    if not apply and stats["memberships_created"] > 0:
        print("\nRe-run with --apply to execute these changes.")


if __name__ == "__main__":
    apply_flag = "--apply" in sys.argv
    migrate(apply=apply_flag)
