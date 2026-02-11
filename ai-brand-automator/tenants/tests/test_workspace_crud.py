"""
Workspace creation, deletion, and registration mode tests.

Covers:
  - CreateTenantView  (POST /api/v1/tenants/create/)
  - DeleteTenantView  (DELETE /api/v1/tenants/<id>/delete/)
  - Registration modes (brand owner signup creates tenant + OWNER membership)
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Membership, Tenant

User = get_user_model()


# ── helpers ─────────────────────────────────────────────────────────


def _make_client(user, tenant=None):
    """Build an authenticated API client, optionally with X-Tenant-ID."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    if tenant:
        client.credentials(HTTP_X_TENANT_ID=str(tenant.id))
    return client


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def ws_user(db):
    return User.objects.create_user(
        username="ws_user", email="ws@test.com", password="TestPass123!"
    )


@pytest.fixture
def ws_user2(db):
    return User.objects.create_user(
        username="ws_user2", email="ws2@test.com", password="TestPass123!"
    )


# ── CreateTenantView Tests ─────────────────────────────────────────


@pytest.mark.django_db
class TestCreateWorkspace:
    """POST /api/v1/tenants/create/"""

    def test_authenticated_user_can_create_workspace(self, ws_user):
        """Any authenticated user can create a workspace."""
        client = _make_client(ws_user)
        resp = client.post(
            "/api/v1/tenants/create/",
            {"name": "My New Workspace"},
        )
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "My New Workspace"

    def test_creator_becomes_owner(self, ws_user):
        """Workspace creator automatically gets OWNER membership."""
        client = _make_client(ws_user)
        resp = client.post(
            "/api/v1/tenants/create/",
            {"name": "Owner Check WS"},
        )
        assert resp.status_code == status.HTTP_201_CREATED

        tenant = Tenant.objects.get(name="Owner Check WS")
        m = Membership.objects.get(user=ws_user, tenant=tenant)
        assert m.role == "owner"
        assert m.is_active is True
        assert m.accepted_at is not None

    def test_workspace_has_domain_and_slug(self, ws_user):
        """Created workspace gets a slug and a domain."""
        client = _make_client(ws_user)
        resp = client.post(
            "/api/v1/tenants/create/",
            {"name": "Slug Test WS"},
        )
        assert resp.status_code == status.HTTP_201_CREATED

        tenant = Tenant.objects.get(name="Slug Test WS")
        assert tenant.slug == "slug-test-ws"
        assert tenant.domains.count() == 1

    def test_duplicate_name_returns_409(self, ws_user):
        """Creating a workspace with a duplicate name → 409."""
        client = _make_client(ws_user)
        client.post("/api/v1/tenants/create/", {"name": "Dup Workspace"})
        resp = client.post("/api/v1/tenants/create/", {"name": "Dup Workspace"})
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_empty_name_returns_400(self, ws_user):
        """Empty workspace name → 400."""
        client = _make_client(ws_user)
        resp = client.post("/api/v1/tenants/create/", {"name": ""})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_name_returns_400(self, ws_user):
        """Missing name field → 400."""
        client = _make_client(ws_user)
        resp = client.post("/api/v1/tenants/create/", {})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_cannot_create_workspace(self):
        """Unauthenticated user gets 401."""
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        resp = client.post("/api/v1/tenants/create/", {"name": "Unauth WS"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_user_can_create_multiple_workspaces(self, ws_user):
        """Same user can own multiple workspaces."""
        client = _make_client(ws_user)
        resp1 = client.post("/api/v1/tenants/create/", {"name": "Multi WS 1"})
        resp2 = client.post("/api/v1/tenants/create/", {"name": "Multi WS 2"})
        assert resp1.status_code == status.HTTP_201_CREATED
        assert resp2.status_code == status.HTTP_201_CREATED

        # User should have 2 OWNER memberships
        owner_count = Membership.objects.filter(
            user=ws_user, role=Membership.Role.OWNER
        ).count()
        assert owner_count == 2


# ── DeleteTenantView Tests ─────────────────────────────────────────


@pytest.mark.django_db
class TestDeleteWorkspace:
    """DELETE /api/v1/tenants/<id>/delete/"""

    def test_owner_can_delete_workspace(self, ws_user):
        """OWNER can delete the workspace."""
        client = _make_client(ws_user)
        resp = client.post("/api/v1/tenants/create/", {"name": "Delete Me WS"})
        assert resp.status_code == status.HTTP_201_CREATED
        tenant = Tenant.objects.get(name="Delete Me WS")

        del_client = _make_client(ws_user, tenant)
        resp = del_client.delete(f"/api/v1/tenants/{tenant.id}/delete/")
        assert resp.status_code == status.HTTP_200_OK
        assert not Tenant.objects.filter(name="Delete Me WS").exists()

    def test_admin_cannot_delete_workspace(self, ws_user, ws_user2):
        """ADMIN cannot delete workspace (only OWNER can)."""
        client = _make_client(ws_user)
        resp = client.post("/api/v1/tenants/create/", {"name": "No Admin Delete WS"})
        tenant = Tenant.objects.get(name="No Admin Delete WS")

        # Add ws_user2 as ADMIN
        Membership.objects.create(
            user=ws_user2, tenant=tenant, role=Membership.Role.ADMIN
        )

        admin_client = _make_client(ws_user2, tenant)
        resp = admin_client.delete(f"/api/v1/tenants/{tenant.id}/delete/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert Tenant.objects.filter(name="No Admin Delete WS").exists()

    def test_cannot_delete_public_tenant(self, ws_user):
        """Public tenant cannot be deleted."""
        pt = Tenant.objects.get(schema_name="public")
        # Ensure user is owner of public tenant
        Membership.objects.get_or_create(
            user=ws_user,
            tenant=pt,
            defaults={"role": Membership.Role.OWNER},
        )

        client = _make_client(ws_user, pt)
        resp = client.delete(f"/api/v1/tenants/{pt.id}/delete/")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert Tenant.objects.filter(schema_name="public").exists()


# ── Registration Mode Tests ────────────────────────────────────────


@pytest.mark.django_db
class TestRegistrationModes:
    """
    Registration modes for workspace onboarding.

    - Brand owner signup: user registers → creates workspace → becomes OWNER
    - Invite-based: existing user invited → membership created
    - New user invite: unknown email invited → pending membership
    """

    def test_brand_owner_signup_creates_workspace_and_membership(self, ws_user):
        """
        Simulate brand owner signup:
          1. User registers (already done via fixture)
          2. User creates workspace → becomes OWNER
        """
        client = _make_client(ws_user)
        resp = client.post(
            "/api/v1/tenants/create/",
            {"name": "Brand Owner WS"},
        )
        assert resp.status_code == status.HTTP_201_CREATED

        tenant = Tenant.objects.get(name="Brand Owner WS")
        membership = Membership.objects.get(user=ws_user, tenant=tenant)
        assert membership.role == "owner"
        assert membership.is_active is True

        # The workspace shows up in the user's tenant list
        list_client = APIClient()
        list_client.defaults["SERVER_NAME"] = "localhost"
        list_client.force_authenticate(user=ws_user)
        resp = list_client.get("/api/v1/tenants/me/")
        tenant_names = [t["name"] for t in resp.data]
        assert "Brand Owner WS" in tenant_names

    def test_existing_user_invite_creates_active_membership(self, ws_user, ws_user2):
        """
        Existing user invite:
          1. Owner creates workspace
          2. Owner invites ws_user2 (who exists)
          3. ws_user2 gets active membership immediately
        """
        client = _make_client(ws_user)
        client.post("/api/v1/tenants/create/", {"name": "Invite Existing WS"})
        tenant = Tenant.objects.get(name="Invite Existing WS")

        invite_client = _make_client(ws_user, tenant)
        resp = invite_client.post(
            f"/api/v1/tenants/{tenant.id}/members/invite/",
            {"email": ws_user2.email, "role": "editor"},
        )
        assert resp.status_code == status.HTTP_201_CREATED

        m = Membership.objects.get(user=ws_user2, tenant=tenant)
        assert m.role == "editor"
        assert m.is_active is True
        assert m.invited_by == ws_user

    def test_new_user_invite_creates_pending_membership(self, ws_user):
        """
        New user invite:
          1. Owner creates workspace
          2. Owner invites unknown email
          3. Pending membership created (user=None)
        """
        client = _make_client(ws_user)
        client.post("/api/v1/tenants/create/", {"name": "Invite New WS"})
        tenant = Tenant.objects.get(name="Invite New WS")

        invite_client = _make_client(ws_user, tenant)
        resp = invite_client.post(
            f"/api/v1/tenants/{tenant.id}/members/invite/",
            {"email": "newbie@external.com", "role": "viewer"},
        )
        assert resp.status_code == status.HTTP_201_CREATED

        m = Membership.objects.get(invited_email="newbie@external.com", tenant=tenant)
        assert m.user is None
        assert m.is_active is False
        assert m.role == "viewer"
