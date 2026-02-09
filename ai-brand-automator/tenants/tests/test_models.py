"""
Tests for Tenant and Domain models.
"""

import pytest
from django.db import connection

from tenants.models import Domain, Tenant


@pytest.mark.django_db
class TestTenantModel:
    """Tests for the Tenant model."""

    def test_create_tenant(self):
        """Can create a tenant with auto-generated schema_name."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Model Test Co")
        assert tenant.schema_name.startswith("tenant_")
        assert tenant.subscription_status == "trial"
        assert tenant.max_users == 10
        assert tenant.storage_limit_gb == 5

    def test_str_representation(self):
        """__str__ returns tenant name."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Str Test Co")
        assert str(tenant) == "Str Test Co"

    def test_is_subscription_active_trial(self):
        """Trial subscription is considered active."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Trial Co")
        assert tenant.is_subscription_active is True

    def test_is_subscription_active_canceled(self):
        """Canceled subscription is not active."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(
            name="Canceled Co", subscription_status="canceled"
        )
        assert tenant.is_subscription_active is False

    def test_schema_name_uniqueness(self):
        """Two tenants with similar names get different schema names."""
        connection.set_schema_to_public()
        t1 = Tenant.objects.create(name="Unique Co")
        t2 = Tenant.objects.create(name="Unique-Co")
        assert t1.schema_name != t2.schema_name

    def test_schema_name_sanitized(self):
        """Schema name replaces special characters with underscores."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="My Company! #1")
        assert "tenant_my_company" in tenant.schema_name
        # Should not contain special chars
        assert "!" not in tenant.schema_name
        assert "#" not in tenant.schema_name


@pytest.mark.django_db
class TestDomainModel:
    """Tests for the Domain model."""

    def test_create_domain(self):
        """Can create a domain linked to a tenant."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Domain Model Co")
        domain = Domain.objects.create(
            domain="domainmodel.test.com",
            tenant=tenant,
            is_primary=True,
        )
        assert domain.domain == "domainmodel.test.com"
        assert domain.tenant == tenant
        assert domain.is_primary is True

    def test_tenant_domains_relation(self):
        """Tenant has access to its domains via reverse relation."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Relation Co")
        Domain.objects.create(domain="primary.test.com", tenant=tenant, is_primary=True)
        Domain.objects.create(
            domain="secondary.test.com", tenant=tenant, is_primary=False
        )
        assert tenant.domains.count() == 2
