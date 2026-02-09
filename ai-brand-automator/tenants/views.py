"""
Views for the Tenants app.

Provides DRF ViewSets for Tenant and Domain CRUD operations.
Admin-only access — only superusers and staff can manage tenants.
"""

import logging

from django.db import connection
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Domain, Tenant
from .serializers import (
    DomainSerializer,
    TenantCreateSerializer,
    TenantSerializer,
    TenantUpdateSerializer,
)

logger = logging.getLogger(__name__)


class TenantViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for Tenant management.

    Only admin/staff users can manage tenants.
    Tenant creation triggers schema creation via django-tenants.

    Actions:
        list    — GET  /api/v1/tenants/
        create  — POST /api/v1/tenants/
        retrieve — GET /api/v1/tenants/{id}/
        update  — PUT  /api/v1/tenants/{id}/
        partial_update — PATCH /api/v1/tenants/{id}/
        destroy — DELETE /api/v1/tenants/{id}/
        stats   — GET  /api/v1/tenants/{id}/stats/
    """

    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        """Return all tenants with prefetched domains."""
        return Tenant.objects.prefetch_related("domains").all().order_by("-created_at")

    def get_serializer_class(self):
        """Return action-specific serializer."""
        if self.action == "create":
            return TenantCreateSerializer
        if self.action in ("update", "partial_update"):
            return TenantUpdateSerializer
        return TenantSerializer

    def perform_create(self, serializer):
        """Create tenant — schema is auto-created by django-tenants."""
        tenant = serializer.save()
        logger.info("Tenant created: %s (schema: %s)", tenant.name, tenant.schema_name)

    def perform_destroy(self, instance):
        """Delete tenant record.

        Removes the tenant row and associated domains. Schema cleanup
        should be handled separately via a management command.
        The public schema is never deleted.
        """
        if instance.schema_name == "public":
            logger.warning("Attempted to delete the public tenant — blocked.")
            return
        tenant_name = instance.name
        schema_name = instance.schema_name
        instance.delete()
        logger.info("Tenant deleted: %s (schema: %s)", tenant_name, schema_name)

    def destroy(self, request, *args, **kwargs):
        """Override destroy to prevent deletion of the public tenant."""
        instance = self.get_object()
        if instance.schema_name == "public":
            return Response(
                {"detail": "The public tenant cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Return tenant statistics: domain count, subscription status."""
        tenant = self.get_object()
        domain_count = tenant.domains.count()
        # Reset connection to public schema after reading
        connection.set_schema_to_public()
        return Response(
            {
                "id": tenant.id,
                "name": tenant.name,
                "schema_name": tenant.schema_name,
                "subscription_status": tenant.subscription_status,
                "is_subscription_active": tenant.is_subscription_active,
                "domain_count": domain_count,
                "max_users": tenant.max_users,
                "storage_limit_gb": tenant.storage_limit_gb,
            }
        )


class DomainViewSet(viewsets.ModelViewSet):
    """
    CRUD ViewSet for Domain management.

    Domains map hostnames to tenants. Each tenant can have multiple
    domains, but only one primary domain.

    Actions:
        list    — GET  /api/v1/tenants/domains/
        create  — POST /api/v1/tenants/domains/
        retrieve — GET /api/v1/tenants/domains/{id}/
        update  — PUT  /api/v1/tenants/domains/{id}/
        partial_update — PATCH /api/v1/tenants/domains/{id}/
        destroy — DELETE /api/v1/tenants/domains/{id}/
    """

    serializer_class = DomainSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        """Return all domains with their tenant."""
        return Domain.objects.select_related("tenant").all().order_by("domain")

    def perform_create(self, serializer):
        """Create domain — validate tenant exists."""
        domain = serializer.save()
        logger.info("Domain created: %s → tenant %s", domain.domain, domain.tenant.name)
