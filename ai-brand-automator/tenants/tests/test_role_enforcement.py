"""
Role enforcement integration tests.

Verifies the full RBAC matrix across real API endpoints:
  OWNER  → full access
  ADMIN  → admin-level access
  EDITOR → editor-level access (no admin actions)
  VIEWER → read-only (no write actions)
  No membership → 403

Uses the ``CompanyViewSet`` and ``BrandAssetViewSet`` from onboarding
because they define ``role_permissions`` with per-action permission
classes via ``RoleBasedPermissionMixin``.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Membership, Tenant

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
def owner_user(db):
    return User.objects.create_user(
        username="role_owner", email="owner@role.test", password="TestPass123!"
    )


@pytest.fixture
def admin_user_role(db):
    return User.objects.create_user(
        username="role_admin", email="admin@role.test", password="TestPass123!"
    )


@pytest.fixture
def editor_user(db):
    return User.objects.create_user(
        username="role_editor", email="editor@role.test", password="TestPass123!"
    )


@pytest.fixture
def viewer_user(db):
    return User.objects.create_user(
        username="role_viewer", email="viewer@role.test", password="TestPass123!"
    )


@pytest.fixture
def outsider_user(db):
    """User with NO membership in the test tenant."""
    return User.objects.create_user(
        username="outsider", email="outsider@role.test", password="TestPass123!"
    )


@pytest.fixture
def role_tenant(db):
    """Tenant for role enforcement tests."""
    from tenants.models import Domain
    from django.db import connection

    connection.set_schema_to_public()
    t = Tenant.objects.create(
        name="Role-Test Co",
        schema_name="tenant_role_test",
        subscription_status="active",
    )
    Domain.objects.create(domain="roletest.localhost", tenant=t, is_primary=True)
    return t


@pytest.fixture
def role_memberships(
    role_tenant, owner_user, admin_user_role, editor_user, viewer_user
):
    """Create one membership per role in role_tenant."""
    return {
        "owner": Membership.objects.create(
            user=owner_user, tenant=role_tenant, role=Membership.Role.OWNER
        ),
        "admin": Membership.objects.create(
            user=admin_user_role, tenant=role_tenant, role=Membership.Role.ADMIN
        ),
        "editor": Membership.objects.create(
            user=editor_user, tenant=role_tenant, role=Membership.Role.EDITOR
        ),
        "viewer": Membership.objects.create(
            user=viewer_user, tenant=role_tenant, role=Membership.Role.VIEWER
        ),
    }


@pytest.fixture
def company_in_tenant(role_tenant):
    """Create a company inside role_tenant for CRUD tests."""
    from onboarding.models import Company

    return Company.objects.create(
        name="Role Test Company",
        industry="Technology",
        tenant=role_tenant,
    )


# ── CompanyViewSet role enforcement ─────────────────────────────────


@pytest.mark.django_db
class TestCompanyRoleEnforcement:
    """
    CompanyViewSet role_permissions:
      list, retrieve  → IsTenantViewer  (any member)
      create, update  → IsTenantAdmin   (owner, admin)
      generate_*      → IsTenantEditor  (owner, admin, editor)
    """

    # ── list (GET /api/v1/companies/) ──

    def test_owner_can_list_companies(self, role_tenant, role_memberships, owner_user):
        client = _make_client(owner_user, role_tenant)
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_200_OK

    def test_viewer_can_list_companies(
        self, role_tenant, role_memberships, viewer_user
    ):
        client = _make_client(viewer_user, role_tenant)
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_200_OK

    def test_outsider_cannot_list_companies(
        self, role_tenant, role_memberships, outsider_user
    ):
        client = _make_client(outsider_user, role_tenant)
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    # ── create (POST /api/v1/companies/) ──

    def test_owner_can_create_company(self, role_tenant, role_memberships, owner_user):
        client = _make_client(owner_user, role_tenant)
        data = {"name": "New Co Owner", "industry": "SaaS"}
        resp = client.post("/api/v1/companies/", data)
        assert resp.status_code == status.HTTP_201_CREATED

    def test_admin_can_create_company(
        self, role_tenant, role_memberships, admin_user_role
    ):
        client = _make_client(admin_user_role, role_tenant)
        data = {"name": "New Co Admin", "industry": "SaaS"}
        resp = client.post("/api/v1/companies/", data)
        assert resp.status_code == status.HTTP_201_CREATED

    def test_editor_cannot_create_company(
        self, role_tenant, role_memberships, editor_user
    ):
        client = _make_client(editor_user, role_tenant)
        data = {"name": "New Co Editor", "industry": "SaaS"}
        resp = client.post("/api/v1/companies/", data)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_create_company(
        self, role_tenant, role_memberships, viewer_user
    ):
        client = _make_client(viewer_user, role_tenant)
        data = {"name": "New Co Viewer", "industry": "SaaS"}
        resp = client.post("/api/v1/companies/", data)
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    # ── retrieve (GET /api/v1/companies/{id}/) ──

    def test_viewer_can_retrieve_company(
        self, role_tenant, role_memberships, viewer_user, company_in_tenant
    ):
        client = _make_client(viewer_user, role_tenant)
        resp = client.get(f"/api/v1/companies/{company_in_tenant.id}/")
        assert resp.status_code == status.HTTP_200_OK

    def test_outsider_cannot_retrieve_company(
        self, role_tenant, role_memberships, outsider_user, company_in_tenant
    ):
        client = _make_client(outsider_user, role_tenant)
        resp = client.get(f"/api/v1/companies/{company_in_tenant.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    # ── update (PATCH /api/v1/companies/{id}/) ──

    def test_admin_can_update_company(
        self, role_tenant, role_memberships, admin_user_role, company_in_tenant
    ):
        client = _make_client(admin_user_role, role_tenant)
        resp = client.patch(
            f"/api/v1/companies/{company_in_tenant.id}/",
            {"description": "Updated by admin"},
        )
        assert resp.status_code == status.HTTP_200_OK

    def test_editor_cannot_update_company(
        self, role_tenant, role_memberships, editor_user, company_in_tenant
    ):
        client = _make_client(editor_user, role_tenant)
        resp = client.patch(
            f"/api/v1/companies/{company_in_tenant.id}/",
            {"description": "Updated by editor"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_viewer_cannot_update_company(
        self, role_tenant, role_memberships, viewer_user, company_in_tenant
    ):
        client = _make_client(viewer_user, role_tenant)
        resp = client.patch(
            f"/api/v1/companies/{company_in_tenant.id}/",
            {"description": "Updated by viewer"},
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    # ── delete (DELETE /api/v1/companies/{id}/) ──

    def test_owner_can_delete_company(
        self, role_tenant, role_memberships, owner_user, company_in_tenant
    ):
        client = _make_client(owner_user, role_tenant)
        resp = client.delete(f"/api/v1/companies/{company_in_tenant.id}/")
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_editor_cannot_delete_company(
        self, role_tenant, role_memberships, editor_user, company_in_tenant
    ):
        client = _make_client(editor_user, role_tenant)
        resp = client.delete(f"/api/v1/companies/{company_in_tenant.id}/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


# ── Multi-tenant user: different roles per tenant ───────────────────


@pytest.mark.django_db
class TestMultiTenantUserRoles:
    """User is OWNER of Tenant A and EDITOR of Tenant B.

    Critical scenario from Phase 10 plan:
    can create content in both, can only admin in A.
    """

    @pytest.fixture
    def tenant_b(self, db):
        from tenants.models import Domain
        from django.db import connection

        connection.set_schema_to_public()
        t = Tenant.objects.create(
            name="Multi-B Co",
            schema_name="tenant_multi_b",
            subscription_status="active",
        )
        Domain.objects.create(domain="multib.localhost", tenant=t, is_primary=True)
        return t

    def test_owner_in_a_can_create_company(self, role_tenant, tenant_b, owner_user):
        """OWNER of role_tenant → can create company."""
        Membership.objects.get_or_create(
            user=owner_user,
            tenant=role_tenant,
            defaults={"role": Membership.Role.OWNER},
        )
        Membership.objects.get_or_create(
            user=owner_user,
            tenant=tenant_b,
            defaults={"role": Membership.Role.EDITOR},
        )

        client = _make_client(owner_user, role_tenant)
        resp = client.post(
            "/api/v1/companies/", {"name": "A-Company", "industry": "Tech"}
        )
        assert resp.status_code == status.HTTP_201_CREATED

    def test_editor_in_b_cannot_create_company(self, role_tenant, tenant_b, owner_user):
        """EDITOR of tenant_b → cannot create company (admin required)."""
        Membership.objects.get_or_create(
            user=owner_user,
            tenant=role_tenant,
            defaults={"role": Membership.Role.OWNER},
        )
        Membership.objects.get_or_create(
            user=owner_user,
            tenant=tenant_b,
            defaults={"role": Membership.Role.EDITOR},
        )

        client = _make_client(owner_user, tenant_b)
        resp = client.post(
            "/api/v1/companies/", {"name": "B-Company", "industry": "Tech"}
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_editor_in_b_can_list_companies(self, role_tenant, tenant_b, owner_user):
        """EDITOR of tenant_b → can list companies (viewer access)."""
        Membership.objects.get_or_create(
            user=owner_user,
            tenant=role_tenant,
            defaults={"role": Membership.Role.OWNER},
        )
        Membership.objects.get_or_create(
            user=owner_user,
            tenant=tenant_b,
            defaults={"role": Membership.Role.EDITOR},
        )

        client = _make_client(owner_user, tenant_b)
        resp = client.get("/api/v1/companies/")
        assert resp.status_code == status.HTTP_200_OK
