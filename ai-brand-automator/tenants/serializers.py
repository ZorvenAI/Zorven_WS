"""
Serializers for the Tenants app.

Provides DRF serializers for Tenant and Domain CRUD operations.
"""

import re

from rest_framework import serializers

from .models import Domain, Tenant


class DomainSerializer(serializers.ModelSerializer):
    """Serializer for tenant domains."""

    class Meta:
        model = Domain
        fields = ["id", "domain", "tenant", "is_primary"]
        read_only_fields = ["id"]


class DomainNestedSerializer(serializers.ModelSerializer):
    """Read-only nested serializer for domains within a tenant."""

    class Meta:
        model = Domain
        fields = ["id", "domain", "is_primary"]
        read_only_fields = ["id", "domain", "is_primary"]


class TenantSerializer(serializers.ModelSerializer):
    """Read serializer for Tenant — includes domains."""

    domains = DomainNestedSerializer(many=True, read_only=True)
    is_subscription_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "description",
            "schema_name",
            "subscription_status",
            "stripe_customer_id",
            "max_users",
            "storage_limit_gb",
            "gcs_raw_bucket",
            "gcs_curated_bucket",
            "is_subscription_active",
            "created_at",
            "updated_at",
            "domains",
        ]
        read_only_fields = [
            "id",
            "schema_name",
            "created_at",
            "updated_at",
            "is_subscription_active",
        ]


class TenantCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new tenant.

    The `schema_name` is auto-generated from `name` if not provided.
    Optionally accepts an initial `domain` to create alongside the tenant.
    """

    domain = serializers.CharField(
        max_length=253,
        required=False,
        write_only=True,
        help_text="Initial domain for this tenant (e.g. 'acme.example.com')",
    )

    class Meta:
        model = Tenant
        fields = [
            "name",
            "description",
            "subscription_status",
            "max_users",
            "storage_limit_gb",
            "gcs_raw_bucket",
            "gcs_curated_bucket",
            "domain",
        ]

    def validate_name(self, value):
        """Ensure tenant name is unique (case-insensitive)."""
        if Tenant.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A tenant with this name already exists.")
        return value

    def validate_domain(self, value):
        """Validate domain format and uniqueness."""
        value = value.strip().lower()
        # Basic domain format validation
        domain_regex = re.compile(
            r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*$"
        )
        if not domain_regex.match(value):
            raise serializers.ValidationError("Invalid domain format.")
        if Domain.objects.filter(domain=value).exists():
            raise serializers.ValidationError(
                "This domain is already registered to another tenant."
            )
        return value

    def create(self, validated_data):
        """Create tenant and optional initial domain."""
        domain_name = validated_data.pop("domain", None)
        tenant = Tenant(**validated_data)
        # We use shared-schema multi-tenancy (FK filtering), so
        # prevent django-tenants from creating a separate PG schema.
        tenant.auto_create_schema = False
        tenant.save()  # Triggers schema_name auto-generation

        # Create initial domain if provided
        if domain_name:
            Domain.objects.create(
                domain=domain_name,
                tenant=tenant,
                is_primary=True,
            )

        return tenant


class TenantUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating an existing tenant.

    `name` and `schema_name` are NOT editable after creation.
    """

    class Meta:
        model = Tenant
        fields = [
            "description",
            "subscription_status",
            "max_users",
            "storage_limit_gb",
            "gcs_raw_bucket",
            "gcs_curated_bucket",
        ]
