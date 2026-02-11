"""
Unit tests for role-based permission classes.

Tests each permission class with every role to verify the RBAC matrix:
    OWNER  → all access
    ADMIN  → all except owner-only
    EDITOR → view + edit (no admin/owner)
    VIEWER → view only
    None   → no access
"""

from unittest.mock import MagicMock

from tenants.permissions import (
    HasTenantAccess,
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantOwner,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)


def _make_request(membership=None, user_role=None):
    """Build a mock request with membership and user_role attributes."""
    request = MagicMock()
    request.membership = membership
    request.user_role = user_role
    return request


class TestHasTenantAccess:
    """HasTenantAccess — requires any active membership."""

    def test_allows_when_membership_exists(self):
        request = _make_request(membership=MagicMock(), user_role="viewer")
        assert HasTenantAccess().has_permission(request, None) is True

    def test_denies_when_no_membership(self):
        request = _make_request(membership=None, user_role=None)
        assert HasTenantAccess().has_permission(request, None) is False


class TestIsTenantOwner:
    """IsTenantOwner — only OWNER role."""

    def test_allows_owner(self):
        request = _make_request(membership=MagicMock(), user_role="owner")
        assert IsTenantOwner().has_permission(request, None) is True

    def test_denies_admin(self):
        request = _make_request(membership=MagicMock(), user_role="admin")
        assert IsTenantOwner().has_permission(request, None) is False

    def test_denies_editor(self):
        request = _make_request(membership=MagicMock(), user_role="editor")
        assert IsTenantOwner().has_permission(request, None) is False

    def test_denies_viewer(self):
        request = _make_request(membership=MagicMock(), user_role="viewer")
        assert IsTenantOwner().has_permission(request, None) is False

    def test_denies_no_role(self):
        request = _make_request(membership=None, user_role=None)
        assert IsTenantOwner().has_permission(request, None) is False


class TestIsTenantAdmin:
    """IsTenantAdmin — OWNER or ADMIN."""

    def test_allows_owner(self):
        request = _make_request(membership=MagicMock(), user_role="owner")
        assert IsTenantAdmin().has_permission(request, None) is True

    def test_allows_admin(self):
        request = _make_request(membership=MagicMock(), user_role="admin")
        assert IsTenantAdmin().has_permission(request, None) is True

    def test_denies_editor(self):
        request = _make_request(membership=MagicMock(), user_role="editor")
        assert IsTenantAdmin().has_permission(request, None) is False

    def test_denies_viewer(self):
        request = _make_request(membership=MagicMock(), user_role="viewer")
        assert IsTenantAdmin().has_permission(request, None) is False

    def test_denies_no_role(self):
        request = _make_request(membership=None, user_role=None)
        assert IsTenantAdmin().has_permission(request, None) is False


class TestIsTenantEditor:
    """IsTenantEditor — OWNER, ADMIN, or EDITOR."""

    def test_allows_owner(self):
        request = _make_request(membership=MagicMock(), user_role="owner")
        assert IsTenantEditor().has_permission(request, None) is True

    def test_allows_admin(self):
        request = _make_request(membership=MagicMock(), user_role="admin")
        assert IsTenantEditor().has_permission(request, None) is True

    def test_allows_editor(self):
        request = _make_request(membership=MagicMock(), user_role="editor")
        assert IsTenantEditor().has_permission(request, None) is True

    def test_denies_viewer(self):
        request = _make_request(membership=MagicMock(), user_role="viewer")
        assert IsTenantEditor().has_permission(request, None) is False

    def test_denies_no_role(self):
        request = _make_request(membership=None, user_role=None)
        assert IsTenantEditor().has_permission(request, None) is False


class TestIsTenantViewer:
    """IsTenantViewer — any active membership (alias for HasTenantAccess)."""

    def test_allows_owner(self):
        request = _make_request(membership=MagicMock(), user_role="owner")
        assert IsTenantViewer().has_permission(request, None) is True

    def test_allows_admin(self):
        request = _make_request(membership=MagicMock(), user_role="admin")
        assert IsTenantViewer().has_permission(request, None) is True

    def test_allows_editor(self):
        request = _make_request(membership=MagicMock(), user_role="editor")
        assert IsTenantViewer().has_permission(request, None) is True

    def test_allows_viewer(self):
        request = _make_request(membership=MagicMock(), user_role="viewer")
        assert IsTenantViewer().has_permission(request, None) is True

    def test_denies_no_membership(self):
        request = _make_request(membership=None, user_role=None)
        assert IsTenantViewer().has_permission(request, None) is False


class TestRoleBasedPermissionMixin:
    """RoleBasedPermissionMixin dispatches per-action permission classes."""

    def test_returns_action_specific_permissions(self):
        """If action is in role_permissions, return those permissions."""

        class FakeViewSet(RoleBasedPermissionMixin):
            role_permissions = {
                "create": [IsTenantAdmin],
                "list": [IsTenantViewer],
            }
            permission_classes = [HasTenantAccess]
            action = "create"

            def get_permissions(self_inner):
                return super(FakeViewSet, self_inner).get_permissions()

        vs = FakeViewSet()
        perms = vs.get_permissions()
        assert len(perms) == 1
        assert isinstance(perms[0], IsTenantAdmin)

    def test_falls_through_for_unlisted_action(self):
        """Actions not in role_permissions use the default."""
        from rest_framework.viewsets import ModelViewSet

        class FakeViewSet(RoleBasedPermissionMixin, ModelViewSet):
            role_permissions = {
                "create": [IsTenantAdmin],
            }
            permission_classes = [HasTenantAccess]
            action = "retrieve"  # Not in role_permissions

        vs = FakeViewSet()
        perms = vs.get_permissions()
        # Should fall back to permission_classes
        assert len(perms) == 1
        assert isinstance(perms[0], HasTenantAccess)

    def test_empty_role_permissions(self):
        """Empty role_permissions always falls through."""
        from rest_framework.viewsets import ModelViewSet

        class FakeViewSet(RoleBasedPermissionMixin, ModelViewSet):
            role_permissions = {}
            permission_classes = [HasTenantAccess]
            action = "list"

        vs = FakeViewSet()
        perms = vs.get_permissions()
        assert isinstance(perms[0], HasTenantAccess)
