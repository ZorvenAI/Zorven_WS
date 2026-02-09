"""
Tests for Tenant serializers.
"""

import pytest
from django.db import connection

from tenants.models import Domain, Tenant
from tenants.serializers import (
    TenantCreateSerializer,
    TenantSerializer,
    TenantUpdateSerializer,
)


@pytest.mark.django_db
class TestTenantSerializer:
    """Tests for the read TenantSerializer."""

    def test_serializes_all_fields(self):
        """Tenant serializer includes all expected fields."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Serializer Test Co")
        Domain.objects.create(domain="ser.test.com", tenant=tenant, is_primary=True)
        serializer = TenantSerializer(tenant)
        data = serializer.data

        assert data["name"] == "Serializer Test Co"
        assert "schema_name" in data
        assert "domains" in data
        assert len(data["domains"]) == 1
        assert data["domains"][0]["domain"] == "ser.test.com"
        assert data["is_subscription_active"] is True  # default is trial
        assert "created_at" in data
        assert "updated_at" in data

    def test_schema_name_is_read_only(self):
        """schema_name cannot be set via serializer."""
        serializer = TenantSerializer()
        assert "schema_name" in serializer.Meta.read_only_fields


@pytest.mark.django_db
class TestTenantCreateSerializer:
    """Tests for the TenantCreateSerializer."""

    def test_valid_creation(self):
        """Create tenant with valid data."""
        connection.set_schema_to_public()
        data = {"name": "Acme Corp", "description": "Test company"}
        serializer = TenantCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        tenant = serializer.save()
        assert tenant.name == "Acme Corp"
        assert tenant.schema_name.startswith("tenant_")
        assert tenant.subscription_status == "trial"

    def test_creation_with_domain(self):
        """Create tenant with an initial domain."""
        connection.set_schema_to_public()
        data = {
            "name": "Domain Test Co",
            "domain": "domaintest.example.com",
        }
        serializer = TenantCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        tenant = serializer.save()
        assert tenant.domains.count() == 1
        assert tenant.domains.first().domain == "domaintest.example.com"
        assert tenant.domains.first().is_primary is True

    def test_duplicate_name_rejected(self):
        """Cannot create two tenants with the same name (case-insensitive)."""
        connection.set_schema_to_public()
        Tenant.objects.create(name="Unique Co")
        data = {"name": "unique co"}
        serializer = TenantCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "name" in serializer.errors

    def test_duplicate_domain_rejected(self):
        """Cannot use a domain already assigned to another tenant."""
        connection.set_schema_to_public()
        existing = Tenant.objects.create(name="Existing Co")
        Domain.objects.create(
            domain="taken.example.com", tenant=existing, is_primary=True
        )
        data = {"name": "New Co", "domain": "taken.example.com"}
        serializer = TenantCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "domain" in serializer.errors

    def test_invalid_domain_format_rejected(self):
        """Domain must be a valid hostname."""
        data = {"name": "Bad Domain Co", "domain": "not a valid domain!"}
        serializer = TenantCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "domain" in serializer.errors

    def test_schema_name_auto_generated(self):
        """Schema name is auto-generated from tenant name."""
        connection.set_schema_to_public()
        data = {"name": "My Test Company!"}
        serializer = TenantCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        tenant = serializer.save()
        assert tenant.schema_name == "tenant_my_test_company_"

    def test_schema_name_collision_avoidance(self):
        """Duplicate schema names get a counter suffix."""
        connection.set_schema_to_public()
        Tenant.objects.create(name="Collision Co")
        # Create a second tenant whose name would generate the same schema
        data = {"name": "Collision-Co"}
        serializer = TenantCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        tenant = serializer.save()
        # Should have a suffix to avoid collision
        assert tenant.schema_name != "tenant_collision_co"


@pytest.mark.django_db
class TestTenantUpdateSerializer:
    """Tests for the TenantUpdateSerializer."""

    def test_can_update_description(self):
        """Description is editable."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Update Co")
        serializer = TenantUpdateSerializer(
            tenant, data={"description": "Updated"}, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.description == "Updated"

    def test_can_update_subscription_status(self):
        """Subscription status is editable."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Sub Update Co")
        serializer = TenantUpdateSerializer(
            tenant, data={"subscription_status": "active"}, partial=True
        )
        assert serializer.is_valid(), serializer.errors
        updated = serializer.save()
        assert updated.subscription_status == "active"

    def test_name_not_editable(self):
        """Name field is not in the update serializer."""
        fields = TenantUpdateSerializer.Meta.fields
        assert "name" not in fields
        assert "schema_name" not in fields
