#!/usr/bin/env python
"""
Add production domains to the public tenant.
This allows Railway and other production domains to work with django-tenants.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from tenants.models import Tenant, Domain  # noqa: E402


def add_production_domains():
    """Add production domains to the public tenant"""
    # Get the public tenant
    try:
        public_tenant = Tenant.objects.get(schema_name="public")
    except Tenant.DoesNotExist:
        print("⚠️  Public tenant does not exist. Creating it first...")
        public_tenant = Tenant.objects.create(
            schema_name="public",
            name="Public",
            description="Public schema for authentication and shared data",
        )
        print(f"✅ Created public tenant: {public_tenant.name}")

    # Production domains to add
    production_domains = [
        # Railway production domains
        "previsionws-production.up.railway.app",
        # Railway uses various subdomains
        "*.up.railway.app",
        # Localhost for development
        "localhost",
        "127.0.0.1",
    ]

    for domain_name in production_domains:
        # Skip wildcard domains (django-tenants doesn't support them directly)
        if "*" in domain_name:
            print(f"⏭️  Skipping wildcard domain: {domain_name}")
            continue

        domain, created = Domain.objects.get_or_create(
            domain=domain_name,
            defaults={"tenant": public_tenant, "is_primary": False},
        )
        if created:
            print(f"✅ Added domain: {domain_name}")
        else:
            print(f"⏭️  Domain already exists: {domain_name}")

    # Ensure localhost is primary
    try:
        localhost = Domain.objects.get(domain="localhost")
        if not localhost.is_primary:
            localhost.is_primary = True
            localhost.save()
            print("✅ Set localhost as primary domain")
    except Domain.DoesNotExist:
        Domain.objects.create(
            domain="localhost", tenant=public_tenant, is_primary=True
        )
        print("✅ Created localhost as primary domain")

    print("\n🎉 Production domains added successfully!")


if __name__ == "__main__":
    add_production_domains()
