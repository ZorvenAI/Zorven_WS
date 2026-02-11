"""
Tenant switching and cross-tenant data isolation tests.

Covers Phase 10 critical scenarios:
  1. Cross-tenant data isolation (user sends X-Tenant-ID they don't belong to → 403)
  2. Tenant switching via API (/api/v1/tenants/switch/)
  3. Multi-tenant user sees correct data per tenant
  4. Data does not leak between tenants
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Domain, Membership, Tenant

User = get_user_model()


# ── helpers ─────────────────────────────────────────────────────────


def _make_client(user, tenant):
    """Build an authenticated API client with X-Tenant-ID header."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return client


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def iso_user(db):
    return User.objects.create_user(
        username="iso_user", email="iso@test.com", password="TestPass123!"
    )


@pytest.fixture
def iso_user2(db):
    return User.objects.create_user(
        username="iso_user2", email="iso2@test.com", password="TestPass123!"
    )


@pytest.fixture
def tenant_alpha(db):
    connection.set_schema_to_public()
    t = Tenant.objects.create(
        name="Alpha Co",
        schema_name="tenant_alpha",
        subscription_status="active",
    )
    Domain.objects.create(domain="alpha.localhost", tenant=t, is_primary=True)
    return t


@pytest.fixture
def tenant_beta(db):
    connection.set_schema_to_public()
    t = Tenant.objects.create(
        name="Beta Co",
        schema_name="tenant_beta",
        subscription_status="active",
    )
    Domain.objects.create(domain="beta.localhost", tenant=t, is_primary=True)
    return t


@pytest.fixture
def alpha_company(tenant_alpha):
    from onboarding.models import Company

    return Company.objects.create(
        name="Alpha Company",
        industry="Tech",
        tenant=tenant_alpha,
    )


@pytest.fixture
def beta_company(tenant_beta):
    from onboarding.models import Company

    return Company.objects.create(
        name="Beta Company",
        industry="Finance",
        tenant=tenant_beta,
    )


# ── Cross-Tenant Isolation Tests ───────────────────────────────────


@pytest.mark.django_db
class TestCrossTenantIsolation:
    """User in Tenant A cannot see Tenant B data regardless of header."""

    def test_user_with_alpha_membership_cannot_access_beta(
        self, tenant_alpha, tenant_beta, iso_user, alpha_company, beta_company
    ):
        """User who is EDITOR of Alpha but sends X-Tenant-ID: Beta → 403."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.EDITOR
        )
        # No membership in beta → should get 403
        client = _make_client(iso_user, tenant_beta)
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_user_cannot_retrieve_other_tenant_company(
        self, tenant_alpha, tenant_beta, iso_user, alpha_company, beta_company
    ):
        """User in Alpha cannot retrieve a company object from Beta."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        client = _make_client(iso_user, tenant_alpha)
        # Try to retrieve Beta's company via Alpha's context
        resp = client.get(f"/api/v1/companies/{beta_company.id}/")
        # Should be 404 (filtered out by queryset) not 200
        assert resp.status_code in (
            status.HTTP_404_NOT_FOUND,
            status.HTTP_403_FORBIDDEN,
        )

    def test_user_sees_only_own_tenant_companies(
        self, tenant_alpha, tenant_beta, iso_user, alpha_company, beta_company
    ):
        """User in Alpha sees only Alpha's companies, never Beta's."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        client = _make_client(iso_user, tenant_alpha)
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", resp.data)
        company_names = [c["name"] for c in results]
        assert "Alpha Company" in company_names
        assert "Beta Company" not in company_names

    def test_multi_tenant_user_sees_correct_data_per_tenant(
        self, tenant_alpha, tenant_beta, iso_user, alpha_company, beta_company
    ):
        """User with memberships in two tenants sees correct data when switching."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=iso_user, tenant=tenant_beta, role=Membership.Role.EDITOR
        )

        # Check Alpha
        client_a = _make_client(iso_user, tenant_alpha)
        resp_a = client_a.get("/api/v1/companies/")
        assert resp_a.status_code == status.HTTP_200_OK
        results_a = resp_a.data.get("results", resp_a.data)
        names_a = [c["name"] for c in results_a]
        assert "Alpha Company" in names_a
        assert "Beta Company" not in names_a

        # Check Beta
        client_b = _make_client(iso_user, tenant_beta)
        resp_b = client_b.get("/api/v1/companies/")
        assert resp_b.status_code == status.HTTP_200_OK
        results_b = resp_b.data.get("results", resp_b.data)
        names_b = [c["name"] for c in results_b]
        assert "Beta Company" in names_b
        assert "Alpha Company" not in names_b

    def test_unauthenticated_with_tenant_header_gets_401(self, tenant_alpha):
        """Unauthenticated request with X-Tenant-ID → 401."""
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.credentials(HTTP_X_TENANT_ID=str(tenant_alpha.id))
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


# ── Tenant Switching Tests ──────────────────────────────────────────


@pytest.mark.django_db
class TestTenantSwitching:
    """POST /api/v1/tenants/switch/ — switch active workspace."""

    def test_switch_to_valid_tenant_returns_tokens(
        self, tenant_alpha, tenant_beta, iso_user
    ):
        """User can switch to a tenant they belong to and get new JWT."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=iso_user, tenant=tenant_beta, role=Membership.Role.EDITOR
        )

        # Use Alpha context initially
        client = _make_client(iso_user, tenant_alpha)
        resp = client.post(
            "/api/v1/tenants/switch/",
            {"tenant_id": tenant_beta.id},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert "tokens" in resp.data
        assert "access" in resp.data["tokens"]
        assert "refresh" in resp.data["tokens"]

    def test_switch_returns_correct_active_tenant(
        self, tenant_alpha, tenant_beta, iso_user
    ):
        """Response includes the target tenant info."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=iso_user, tenant=tenant_beta, role=Membership.Role.EDITOR
        )

        client = _make_client(iso_user, tenant_alpha)
        resp = client.post(
            "/api/v1/tenants/switch/",
            {"tenant_id": tenant_beta.id},
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["active_tenant"]["id"] == tenant_beta.id
        assert resp.data["active_tenant"]["name"] == "Beta Co"
        assert resp.data["active_tenant"]["role"] == "editor"

    def test_switch_to_nonmember_tenant_returns_403(
        self, tenant_alpha, tenant_beta, iso_user
    ):
        """Cannot switch to a tenant the user doesn't belong to."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        # No membership in beta

        client = _make_client(iso_user, tenant_alpha)
        resp = client.post(
            "/api/v1/tenants/switch/",
            {"tenant_id": tenant_beta.id},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_switch_to_inactive_membership_returns_403(
        self, tenant_alpha, tenant_beta, iso_user
    ):
        """Cannot switch to a tenant where membership is deactivated."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        m = Membership.objects.create(
            user=iso_user, tenant=tenant_beta, role=Membership.Role.EDITOR
        )
        m.is_active = False
        m.save()

        client = _make_client(iso_user, tenant_alpha)
        resp = client.post(
            "/api/v1/tenants/switch/",
            {"tenant_id": tenant_beta.id},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_switch_without_tenant_id_returns_400(self, tenant_alpha, iso_user):
        """Missing tenant_id in request body → 400."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        client = _make_client(iso_user, tenant_alpha)
        resp = client.post("/api/v1/tenants/switch/", {})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


# ── My Workspaces Tests ─────────────────────────────────────────────


@pytest.mark.django_db
class TestMyTenants:
    """GET /api/v1/tenants/me/ — list user's workspaces."""

    def test_user_sees_own_tenants(self, tenant_alpha, tenant_beta, iso_user):
        """User sees all tenants they're a member of."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        Membership.objects.create(
            user=iso_user, tenant=tenant_beta, role=Membership.Role.EDITOR
        )

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.force_authenticate(user=iso_user)
        resp = client.get("/api/v1/tenants/me/")
        assert resp.status_code == status.HTTP_200_OK
        tenant_names = [t["name"] for t in resp.data]
        assert "Alpha Co" in tenant_names
        assert "Beta Co" in tenant_names

    def test_inactive_memberships_excluded(self, tenant_alpha, tenant_beta, iso_user):
        """Inactive memberships are not shown in workspace list."""
        Membership.objects.create(
            user=iso_user, tenant=tenant_alpha, role=Membership.Role.OWNER
        )
        m = Membership.objects.create(
            user=iso_user, tenant=tenant_beta, role=Membership.Role.EDITOR
        )
        m.is_active = False
        m.save()

        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.force_authenticate(user=iso_user)
        resp = client.get("/api/v1/tenants/me/")
        assert resp.status_code == status.HTTP_200_OK
        tenant_names = [t["name"] for t in resp.data]
        assert "Alpha Co" in tenant_names
        assert "Beta Co" not in tenant_names

    def test_user_with_no_memberships_sees_empty(self, iso_user):
        """User with no memberships sees an empty list."""
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        client.force_authenticate(user=iso_user)
        resp = client.get("/api/v1/tenants/me/")
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == []

    def test_unauthenticated_cannot_list_tenants(self):
        """Unauthenticated user gets 401."""
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        resp = client.get("/api/v1/tenants/me/")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
