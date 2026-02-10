#!/usr/bin/env python
"""
Test script to validate multi-tenancy configuration.
This tests:
1. Tenant creation
2. Domain assignment
3. Schema creation
4. Tenant-specific data isolation
"""

import os
import django
import pytest

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "brand_automator.settings")
django.setup()

from tenants.models import Tenant, Domain  # noqa: E402
from django.db import connection  # noqa: E402


@pytest.fixture
def tenant(db):
    """Fixture to create a test tenant"""
    tenant = Tenant.objects.create(
        name="Test Company Inc",
        description="A test company for multi-tenancy validation",
        subscription_status="trial",
    )
    yield tenant
    # Cleanup
    tenant.delete()


@pytest.mark.django_db
def test_tenant_creation():
    """Test creating a new tenant with auto-generated schema name"""
    print("=" * 80)
    print("TEST 1: Tenant Creation")
    print("=" * 80)

    # Create a test tenant
    tenant = Tenant.objects.create(
        name="Test Company Inc",
        description="A test company for multi-tenancy validation",
        subscription_status="trial",
    )

    print("✅ Tenant created successfully!")
    print(f"   - ID: {tenant.id}")
    print(f"   - Name: {tenant.name}")
    print(f"   - Schema Name: {tenant.schema_name}")
    print(f"   - Subscription Status: {tenant.subscription_status}")
    print(f"   - Created At: {tenant.created_at}")
    print()

    assert tenant.id is not None
    assert tenant.schema_name.startswith("tenant_")
    tenant.delete()


@pytest.mark.django_db
def test_domain_creation(tenant):
    """Test creating a domain for the tenant"""
    print("=" * 80)
    print("TEST 2: Domain Creation")
    print("=" * 80)

    # Create a domain for localhost testing
    domain = Domain.objects.create(
        domain=f"{tenant.schema_name}.localhost",
        tenant=tenant,
        is_primary=True,
    )

    print("✅ Domain created successfully!")
    print(f"   - Domain: {domain.domain}")
    print(f"   - Tenant: {domain.tenant.name}")
    print(f"   - Is Primary: {domain.is_primary}")
    print()

    assert domain.domain == f"{tenant.schema_name}.localhost"
    assert domain.is_primary is True


@pytest.mark.django_db
def test_schema_not_created(tenant):
    """Test that per-tenant schema is NOT created (shared-schema architecture).

    With ``auto_create_schema = False``, the platform uses FK-based
    isolation on the public schema, so no PostgreSQL schema should be
    created for new tenants.
    """
    print("=" * 80)
    print("TEST 3: Schema Should NOT Exist (shared-schema architecture)")
    print("=" * 80)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name = %s
        """,
            [tenant.schema_name],
        )
        result = cursor.fetchone()

    if result is None:
        print("✅ Schema correctly NOT created (shared-schema mode)!")
    else:
        print("❌ Schema unexpectedly exists!")
        print(f"   - Schema Name: {result[0]}")
    print()

    assert result is None, (
        f"Schema {tenant.schema_name} should not exist " "with auto_create_schema=False"
    )


@pytest.mark.django_db
def test_tenant_data_isolation(tenant):
    """Test that tenant-specific data is isolated via FK filtering.

    With the shared-schema architecture, isolation is enforced by
    filtering on ``tenant`` ForeignKey, not by PostgreSQL schemas.
    """
    print("=" * 80)
    print("TEST 4: Tenant Data Isolation (FK-based)")
    print("=" * 80)

    from onboarding.models import Company

    # Create a second tenant for isolation test
    tenant2 = Tenant.objects.create(
        name="Isolation Test Tenant 2",
        schema_name="isolation_test_2",
        subscription_status="active",
    )

    # Create companies scoped to each tenant
    company1 = Company.objects.create(
        name="Company for Tenant 1",
        tenant=tenant,
    )
    company2 = Company.objects.create(
        name="Company for Tenant 2",
        tenant=tenant2,
    )
    print(f"✅ Created company for tenant 1: {company1.name}")
    print(f"✅ Created company for tenant 2: {company2.name}")

    # Verify isolation via FK filtering
    t1_companies = Company.objects.filter(tenant=tenant)
    t2_companies = Company.objects.filter(tenant=tenant2)
    print(f"   - Companies for tenant 1: {t1_companies.count()}")
    print(f"   - Companies for tenant 2: {t2_companies.count()}")

    assert t1_companies.count() == 1
    assert t2_companies.count() == 1
    assert t1_companies.first().name == "Company for Tenant 1"
    assert t2_companies.first().name == "Company for Tenant 2"

    print("✅ FK-based data isolation working correctly!")
    print()

    # Cleanup
    tenant2.delete()


@pytest.mark.django_db
def test_tenant_listing():
    """List all existing tenants"""
    print("=" * 80)
    print("TEST 5: List All Tenants")
    print("=" * 80)

    tenants = Tenant.objects.all()
    print(f"Total tenants: {tenants.count()}")
    for tenant in tenants:
        domains = Domain.objects.filter(tenant=tenant)
        print(f"\n  Tenant: {tenant.name}")
        print(f"  - Schema: {tenant.schema_name}")
        print(f"  - Status: {tenant.subscription_status}")
        print(f"  - Domains: {', '.join([d.domain for d in domains])}")
    print()


def cleanup_test_data():
    """Clean up test data"""
    print("=" * 80)
    print("CLEANUP: Removing test data")
    print("=" * 80)

    # Remove test tenant
    test_tenants = Tenant.objects.filter(name__icontains="Test Company")
    count = test_tenants.count()
    test_tenants.delete()

    # Remove test users
    from django.contrib.auth.models import User

    User.objects.filter(username__in=["public_user", "tenant_user"]).delete()

    print(f"✅ Cleaned up {count} test tenant(s) and test users")
    print()
