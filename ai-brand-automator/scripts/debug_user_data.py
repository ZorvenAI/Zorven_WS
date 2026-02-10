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
print(f"\nTenant (schema={schema}): {list(tenants.values_list('id', 'schema_name', 'name'))}")

for t in tenants:
    domains = Domain.objects.filter(tenant=t)
    print(f"  Domains: {list(domains.values_list('id', 'domain', 'is_primary'))}")
    companies = Company.objects.filter(tenant=t)
    print(f"  Companies: {list(companies.values_list('id', 'name'))}")
    progress = OnboardingProgress.objects.filter(tenant=t)
    print(f"  OnboardingProgress: {list(progress.values_list('id', 'company__name', 'current_step'))}")
    assets = BrandAsset.objects.filter(tenant=t)
    print(f"  BrandAssets: {list(assets.values_list('id', 'file_name'))}")

# Check public tenant
public = Tenant.objects.filter(schema_name="public").first()
print(f"\nPublic tenant id: {public.id if public else None}")
if public:
    pub_companies = Company.objects.filter(tenant=public)
    print(f"  Companies (public): {list(pub_companies.values_list('id', 'name', 'tenant_id'))}")
    pub_progress = OnboardingProgress.objects.filter(tenant=public)
    print(f"  OnboardingProgress (public): {list(pub_progress.values_list('id', 'company__name', 'current_step'))}")
    pub_assets = BrandAsset.objects.filter(tenant=public)
    print(f"  BrandAssets (public): {list(pub_assets.values_list('id', 'file_name', 'tenant_id'))}")

# Check null tenant
null_companies = Company.objects.filter(tenant__isnull=True)
print(f"\nCompanies with null tenant: {list(null_companies.values_list('id', 'name'))}")

# Check ALL companies
all_companies = Company.objects.all()
print(f"\nAll companies in DB: {list(all_companies.values_list('id', 'name', 'tenant_id'))}")

# Check ALL tenants
all_tenants = Tenant.objects.all().order_by("id")
print(f"\nAll tenants:")
for t in all_tenants:
    has_company = Company.objects.filter(tenant=t).exists()
    print(f"  id={t.id}, schema={t.schema_name}, name={t.name}, has_company={has_company}")

# BrandAssets detail - which company do public tenant assets belong to?
print("\n--- BrandAssets on public tenant (detail) ---")
pub_assets = BrandAsset.objects.filter(tenant=public).select_related("company")
for a in pub_assets:
    print(f"  asset_id={a.id}, file={a.file_name}, company_id={a.company_id}, company={a.company.name if a.company else 'N/A'}")

# OnboardingProgress detail for null-tenant companies
print("\n--- OnboardingProgress for companies with null tenant ---")
for c in null_companies:
    prog = OnboardingProgress.objects.filter(company=c).first()
    if prog:
        print(f"  company_id={c.id}, company={c.name}, step={prog.current_step}, tenant_id={prog.tenant_id}")
    else:
        print(f"  company_id={c.id}, company={c.name}, NO progress record")

# Check OnboardingProgress with null tenant
null_progress = OnboardingProgress.objects.filter(tenant__isnull=True)
print(f"\nOnboardingProgress with null tenant: {list(null_progress.values_list('id', 'company__name', 'current_step'))}")

# All OnboardingProgress
all_progress = OnboardingProgress.objects.all()
print(f"\nAll OnboardingProgress: {list(all_progress.values_list('id', 'company__name', 'current_step', 'tenant_id'))}")
