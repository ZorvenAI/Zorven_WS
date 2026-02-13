"""
Role-based permission classes for tenant membership.

These permissions check the ``request.user_role`` attribute set by
``TenantMembershipMiddleware``.  They are designed to be used on
DRF ViewSets alongside ``IsAuthenticated``.
"""

from rest_framework.permissions import BasePermission


class HasTenantAccess(BasePermission):
    """User must have any active membership in the current tenant."""

    message = "You do not have access to this workspace."

    def has_permission(self, request, view):
        return getattr(request, "membership", None) is not None


class IsTenantOwner(BasePermission):
    """User must be tenant OWNER."""

    message = "Only the workspace owner can perform this action."

    def has_permission(self, request, view):
        return getattr(request, "user_role", None) == "owner"


class IsTenantAdmin(BasePermission):
    """User must be OWNER or ADMIN."""

    message = "Admin access required for this action."

    def has_permission(self, request, view):
        return getattr(request, "user_role", None) in ("owner", "admin")


class IsTenantEditor(BasePermission):
    """User must be OWNER, ADMIN, or EDITOR (not VIEWER)."""

    message = "Editor access required for this action."

    def has_permission(self, request, view):
        return getattr(request, "user_role", None) in (
            "owner",
            "admin",
            "editor",
        )


class IsTenantViewer(BasePermission):
    """User must have any role (even VIEWER). Alias for HasTenantAccess."""

    message = "You do not have access to this workspace."

    def has_permission(self, request, view):
        return getattr(request, "membership", None) is not None


class RoleBasedPermissionMixin:
    """
    Mixin for ViewSets that need different permissions per action.

    Define ``role_permissions`` dict mapping action names to lists of
    permission classes.  Falls through to the default
    ``get_permissions()`` for actions not listed.

    Example::

        class CompanyViewSet(RoleBasedPermissionMixin, ModelViewSet):
            role_permissions = {
                "list": [IsAuthenticated, IsTenantViewer],
                "create": [IsAuthenticated, IsTenantAdmin],
            }
    """

    role_permissions = {}

    def get_permissions(self):
        if self.action in self.role_permissions:
            return [perm() for perm in self.role_permissions[self.action]]
        return super().get_permissions()
