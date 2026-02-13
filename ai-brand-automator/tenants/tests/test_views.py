"""
Tests for Tenant and Domain ViewSets (API endpoints).
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Domain, Tenant

User = get_user_model()


@pytest.fixture
def admin_client(db):
    """API client authenticated as an admin user."""
    connection.set_schema_to_public()
    user = User.objects.create_superuser(
        username="tenantadmin",
        email="admin@test.com",
        password="testpass123",
    )
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def regular_client(db):
    """API client authenticated as a non-admin user."""
    connection.set_schema_to_public()
    user = User.objects.create_user(
        username="regularuser",
        email="user@test.com",
        password="testpass123",
    )
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def unauthenticated_client():
    """API client with no authentication."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    return client


# ─── Tenant CRUD Tests ───────────────────────────────────────────────


@pytest.mark.django_db
class TestTenantList:
    """GET /api/v1/tenants/"""

    def test_admin_can_list_tenants(self, admin_client):
        """Admin user can list all tenants."""
        response = admin_client.get("/api/v1/tenants/")
        assert response.status_code == status.HTTP_200_OK

    def test_non_admin_forbidden(self, regular_client):
        """Non-admin user gets 403."""
        response = regular_client.get("/api/v1/tenants/")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_forbidden(self, unauthenticated_client):
        """Unauthenticated request gets 401."""
        response = unauthenticated_client.get("/api/v1/tenants/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestTenantCreate:
    """POST /api/v1/tenants/"""

    def test_admin_can_create_tenant(self, admin_client):
        """Admin user can create a new tenant."""
        data = {"name": "API Test Co", "description": "Created via API"}
        response = admin_client.post("/api/v1/tenants/", data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Tenant.objects.filter(name="API Test Co").exists()

    def test_create_tenant_with_domain(self, admin_client):
        """Tenant creation with an initial domain."""
        data = {
            "name": "Domain API Co",
            "domain": "domainapi.example.com",
        }
        response = admin_client.post("/api/v1/tenants/", data)
        assert response.status_code == status.HTTP_201_CREATED
        tenant = Tenant.objects.get(name="Domain API Co")
        assert tenant.domains.count() == 1
        assert tenant.domains.first().domain == "domainapi.example.com"

    def test_create_duplicate_name_rejected(self, admin_client):
        """Cannot create tenant with duplicate name."""
        connection.set_schema_to_public()
        Tenant.objects.create(name="Existing API Co")
        data = {"name": "Existing API Co"}
        response = admin_client.post("/api/v1/tenants/", data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_admin_cannot_create(self, regular_client):
        """Non-admin user cannot create tenants."""
        data = {"name": "Forbidden Co"}
        response = regular_client.post("/api/v1/tenants/", data)
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestTenantRetrieve:
    """GET /api/v1/tenants/{id}/"""

    def test_admin_can_retrieve_tenant(self, admin_client):
        """Admin can retrieve a specific tenant."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Retrieve Co")
        response = admin_client.get(f"/api/v1/tenants/{tenant.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Retrieve Co"
        assert "domains" in response.data
        assert "is_subscription_active" in response.data


@pytest.mark.django_db
class TestTenantUpdate:
    """PUT/PATCH /api/v1/tenants/{id}/"""

    def test_admin_can_partial_update(self, admin_client):
        """Admin can PATCH a tenant."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Patch Co")
        response = admin_client.patch(
            f"/api/v1/tenants/{tenant.id}/",
            {"description": "Updated via PATCH"},
        )
        assert response.status_code == status.HTTP_200_OK
        tenant.refresh_from_db()
        assert tenant.description == "Updated via PATCH"

    def test_admin_can_update_subscription(self, admin_client):
        """Admin can change subscription status."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Sub Patch Co")
        response = admin_client.patch(
            f"/api/v1/tenants/{tenant.id}/",
            {"subscription_status": "active"},
        )
        assert response.status_code == status.HTTP_200_OK
        tenant.refresh_from_db()
        assert tenant.subscription_status == "active"


@pytest.mark.django_db
class TestTenantDelete:
    """DELETE /api/v1/tenants/{id}/"""

    def test_admin_can_delete_tenant(self, admin_client):
        """Admin can delete a non-public tenant."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Delete Co")
        tid = tenant.id
        response = admin_client.delete(f"/api/v1/tenants/{tid}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Tenant.objects.filter(id=tid).exists()

    def test_cannot_delete_public_tenant(self, admin_client):
        """Public tenant cannot be deleted."""
        connection.set_schema_to_public()
        public = Tenant.objects.filter(schema_name="public").first()
        if public:
            response = admin_client.delete(f"/api/v1/tenants/{public.id}/")
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert Tenant.objects.filter(id=public.id).exists()


@pytest.mark.django_db
class TestTenantStats:
    """GET /api/v1/tenants/{id}/stats/"""

    def test_admin_can_get_stats(self, admin_client):
        """Admin can get tenant statistics."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Stats Co")
        Domain.objects.create(
            domain="stats.example.com", tenant=tenant, is_primary=True
        )
        response = admin_client.get(f"/api/v1/tenants/{tenant.id}/stats/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Stats Co"
        assert response.data["domain_count"] == 1
        assert response.data["is_subscription_active"] is True


# ─── Domain CRUD Tests ───────────────────────────────────────────────


@pytest.mark.django_db
class TestDomainList:
    """GET /api/v1/tenants/domains/"""

    def test_admin_can_list_domains(self, admin_client):
        """Admin user can list all domains."""
        response = admin_client.get("/api/v1/tenants/domains/")
        assert response.status_code == status.HTTP_200_OK

    def test_non_admin_forbidden(self, regular_client):
        """Non-admin user gets 403."""
        response = regular_client.get("/api/v1/tenants/domains/")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestDomainCreate:
    """POST /api/v1/tenants/domains/"""

    def test_admin_can_create_domain(self, admin_client):
        """Admin can add a domain to an existing tenant."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Domain Target Co")
        data = {
            "domain": "new.example.com",
            "tenant": tenant.id,
            "is_primary": False,
        }
        response = admin_client.post("/api/v1/tenants/domains/", data)
        assert response.status_code == status.HTTP_201_CREATED
        assert Domain.objects.filter(domain="new.example.com").exists()


@pytest.mark.django_db
class TestDomainDelete:
    """DELETE /api/v1/tenants/domains/{id}/"""

    def test_admin_can_delete_domain(self, admin_client):
        """Admin can delete a domain."""
        connection.set_schema_to_public()
        tenant = Tenant.objects.create(name="Domain Del Co")
        domain = Domain.objects.create(
            domain="del.example.com", tenant=tenant, is_primary=True
        )
        response = admin_client.delete(f"/api/v1/tenants/domains/{domain.id}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Domain.objects.filter(id=domain.id).exists()
