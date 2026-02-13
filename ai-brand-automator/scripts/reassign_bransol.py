#!/usr/bin/env python
"""Reassign Bransol company + assets from user_1 tenant to naveen's tenant (user_20)."""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from tenants.models import Tenant  # noqa: E402
from onboarding.models import Company, OnboardingProgress, BrandAsset  # noqa: E402

NAVEEN_TENANT_SCHEMA = "user_20"
COMPANY_ID = 12  # Bransol

# Look up tenants
naveen_tenant = Tenant.objects.get(schema_name=NAVEEN_TENANT_SCHEMA)
print(f"Naveen's tenant: id={naveen_tenant.id}, schema={naveen_tenant.schema_name}")

# Get the company
company = Company.objects.get(id=COMPANY_ID)
old_tenant_id = company.tenant_id
print(
    f"Company: id={company.id}, name={company.name}, current tenant_id={old_tenant_id}"
)

# 1. Reassign Company to naveen's tenant
company.tenant = naveen_tenant
company.save()
print(f"  -> Company reassigned to tenant_id={naveen_tenant.id}")

# 2. Reassign OnboardingProgress
progress = OnboardingProgress.objects.filter(company=company).first()
if progress:
    print(
        f"OnboardingProgress: id={progress.id}, current tenant_id={progress.tenant_id}"
    )
    progress.tenant = naveen_tenant
    progress.save()
    print(f"  -> OnboardingProgress reassigned to tenant_id={naveen_tenant.id}")
else:
    print("No OnboardingProgress found for this company")

# 3. Reassign ALL BrandAssets for this company
assets = BrandAsset.objects.filter(company=company)
print(f"BrandAssets to reassign: {assets.count()}")
updated = assets.update(tenant=naveen_tenant)
print(f"  -> {updated} BrandAssets reassigned to tenant_id={naveen_tenant.id}")

# 4. Also check ChatSessions (ai_services)
from ai_services.models import ChatSession  # noqa: E402

sessions = ChatSession.objects.filter(tenant_id=old_tenant_id)
if sessions.exists():
    count = sessions.update(tenant=naveen_tenant)
    print(f"  -> {count} ChatSessions reassigned to tenant_id={naveen_tenant.id}")
else:
    # Also check public tenant
    public = Tenant.objects.get(schema_name="public")
    pub_sessions = ChatSession.objects.filter(tenant=public)
    if pub_sessions.exists():
        print(f"ChatSessions on public tenant: {pub_sessions.count()}")

# Verify
company.refresh_from_db()
print("\n=== Verification ===")
print(
    f"Company '{company.name}' tenant_id={company.tenant_id}"
    f" (expected {naveen_tenant.id})"
)
prog = OnboardingProgress.objects.filter(company=company).first()
if prog:
    print(
        f"OnboardingProgress tenant_id={prog.tenant_id} (expected {naveen_tenant.id})"
    )
asset_count = BrandAsset.objects.filter(tenant=naveen_tenant).count()
print(f"BrandAssets on naveen's tenant: {asset_count}")
print("\nDone!")
