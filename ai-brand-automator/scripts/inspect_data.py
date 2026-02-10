#!/usr/bin/env python
"""Quick inspection of current tenant/membership/domain state."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")

import django  # noqa: E402

django.setup()

from tenants.models import Tenant, Membership, Domain  # noqa: E402
from onboarding.models import Company  # noqa: E402


def main():
    print("=== TENANTS ===")
    for t in Tenant.objects.all().order_by("id"):
        print(
            f"  T#{t.id:>3}  schema={t.schema_name:<25}  "
            f"slug={t.slug:<20}  name={t.name}"
        )
    print(f"  Total: {Tenant.objects.count()}")

    print("\n=== MEMBERSHIPS ===")
    for m in Membership.objects.select_related("user", "tenant").order_by("id"):
        email = m.user.email if m.user else (m.invited_email or "pending")
        print(
            f"  M#{m.id:>3}  user={email:<35}  "
            f"tenant={m.tenant.name:<20}  role={m.role}  active={m.is_active}"
        )
    print(f"  Total: {Membership.objects.count()}")

    print("\n=== DOMAINS (first 15) ===")
    for d in Domain.objects.all().order_by("id")[:15]:
        print(f"  D#{d.id:>3}  domain={d.domain:<30}  tenant_id={d.tenant_id}")
    print(f"  Total: {Domain.objects.count()}")

    print("\n=== USER-TENANT MAPPING ===")
    user_tenants = {}
    for t in Tenant.objects.all():
        if t.schema_name.startswith("user_"):
            try:
                uid = int(t.schema_name.split("_", 1)[1])
                user_tenants[uid] = t
            except (ValueError, IndexError):
                pass
    print(f"  Tenants with user_N schema: {len(user_tenants)}")
    print("  Of those, have OWNER membership: ", end="")
    has_membership = 0
    for uid, tenant in user_tenants.items():
        if Membership.objects.filter(user_id=uid, tenant=tenant, role="owner").exists():
            has_membership += 1
    print(has_membership)
    print(f"  Missing membership: {len(user_tenants) - has_membership}")

    print("\n=== COMPANIES ===")
    for c in Company.objects.select_related("tenant").all():
        tname = c.tenant.name if c.tenant else "None"
        tschema = c.tenant.schema_name if c.tenant else "None"
        print(f"  C#{c.id:>3}  name={c.name:<30}  tenant={tname} ({tschema})")
    print(f"  Total: {Company.objects.count()}")


if __name__ == "__main__":
    main()
