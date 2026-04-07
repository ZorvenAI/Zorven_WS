"""
Intelligence Loop permission helpers.

Re-exports the standard tenants role permissions and adds a service-token
permission used by the ingest endpoints called from the
intelligence-loop-agent-svc microservice.
"""

from django.conf import settings
from rest_framework.permissions import BasePermission

from tenants.permissions import (  # noqa: F401
    IsTenantAdmin,
    IsTenantEditor,
    IsTenantViewer,
    RoleBasedPermissionMixin,
)


class HasILAServiceToken(BasePermission):
    """Authenticates ILA → Django ingest calls via X-Service-Token header."""

    message = "Invalid or missing X-Service-Token."

    def has_permission(self, request, view):
        expected = getattr(settings, "ILA_SERVICE_TOKEN", "") or ""
        if not expected:
            return False
        provided = request.META.get("HTTP_X_SERVICE_TOKEN", "")
        return bool(provided) and provided == expected
