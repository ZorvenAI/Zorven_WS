"""
Workspace-specific permission helpers.

Re-exports from tenants.permissions for convenience.
"""

from tenants.permissions import (  # noqa: F401
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)
