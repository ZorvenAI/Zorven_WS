#!/usr/bin/env python
"""Debug script to check user's tenant and onboarding data."""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth.models import User  # noqa: E402
from tenants.models import Tenant, Domain  # noqa: E402
from onboarding.models import Company, OnboardingProgress, BrandAsset  # noqa: E402

EMAIL = "naveen.ah@gmail.com"

user = User.objects.get(email=EMAIL)
print(f"User: id={user.id}, email={user.email}, username={user.username}")

# Find tenant
schema = f"user_{user.id}"
tenants = Tenant.objects.filter(schema_name=schema)
vals = list(tenants.values_list("id", "schema_name", "name"))
print(f"\nTenant (schema={schema}): {vals}")

for t in tenants:
    domains = Domain.objects.filter(tenant=t)
    print(f"  Domains: {list(domains.values_list('id', 'domain', 'is_primary'))}")
    companies = Company.objects.filter(tenant=t)
    print(f"  Companies: {list(companies.values_list('id', 'name'))}")
    progress = OnboardingProgress.objects.filter(tenant=t)
    vals = list(progress.values_list("id", "company__name", "current_step"))
    print(f"  OnboardingProgress: {vals}")
    assets = BrandAsset.objects.filter(tenant=t)
    print(f"  BrandAssets: {list(assets.values_list('id', 'file_name'))}")

# Check public tenant
public = Tenant.objects.filter(schema_name="public").first()
print(f"\nPublic tenant id: {public.id if public else None}")
if public:
    pub_companies = Company.objects.filter(tenant=public)
    vals = list(pub_companies.values_list("id", "name", "tenant_id"))
    print(f"  Companies (public): {vals}")
    pub_progress = OnboardingProgress.objects.filter(tenant=public)
    vals = list(pub_progress.values_list("id", "company__name", "current_step"))
    print(f"  OnboardingProgress (public): {vals}")
    pub_assets = BrandAsset.objects.filter(tenant=public)
    vals = list(pub_assets.values_list("id", "file_name", "tenant_id"))
    print(f"  BrandAssets (public): {vals}")

# Check null tenant
null_companies = Company.objects.filter(tenant__isnull=True)
vals = list(null_companies.values_list("id", "name"))
print(f"\nCompanies with null tenant: {vals}")

# Check ALL companies
all_companies = Company.objects.all()
vals = list(all_companies.values_list("id", "name", "tenant_id"))
print(f"\nAll companies in DB: {vals}")

# Check ALL tenants
all_tenants = Tenant.objects.all().order_by("id")
print("\nAll tenants:")
for t in all_tenants:
    has_company = Company.objects.filter(tenant=t).exists()
    print(
        f"  id={t.id}, schema={t.schema_name},"
        f" name={t.name}, has_company={has_company}"
    )

# BrandAssets detail - which company do public tenant assets belong to?
print("\n--- BrandAssets on public tenant (detail) ---")
pub_assets = BrandAsset.objects.filter(tenant=public).select_related("company")
for a in pub_assets:
    company_name = a.company.name if a.company else "N/A"
    print(
        f"  asset_id={a.id}, file={a.file_name},"
        f" company_id={a.company_id}, company={company_name}"
    )

# OnboardingProgress detail for null-tenant companies
print("\n--- OnboardingProgress for companies with null tenant ---")
for c in null_companies:
    prog = OnboardingProgress.objects.filter(company=c).first()
    if prog:
        print(
            f"  company_id={c.id}, company={c.name},"
            f" step={prog.current_step}, tenant_id={prog.tenant_id}"
        )
    else:
        print(f"  company_id={c.id}, company={c.name}, NO progress record")

# Check OnboardingProgress with null tenant
null_progress = OnboardingProgress.objects.filter(tenant__isnull=True)
vals = list(null_progress.values_list("id", "company__name", "current_step"))
print(f"\nOnboardingProgress with null tenant: {vals}")

# All OnboardingProgress
all_progress = OnboardingProgress.objects.all()
vals = list(
    all_progress.values_list("id", "company__name", "current_step", "tenant_id")
)
print(f"\nAll OnboardingProgress: {vals}")
