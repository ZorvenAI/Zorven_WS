"""RBAC permission matrix for prompt optimization (§11.1).

Defines the OWNER/ADMIN/EDITOR/VIEWER role matrix and provides
a FastAPI dependency for role-based access control. Endpoints
wire this dependency via Depends(require_permission(...)).
"""

import logging
from enum import Enum
from typing import Callable, Coroutine, Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """User roles ordered by privilege level."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Operations that require authorization."""

    VIEW = "view"
    REGISTER = "register"
    TRIGGER_OPTIMIZATION = "trigger_optimization"
    APPROVE = "approve"
    PROMOTE = "promote"
    CREATE_OVERRIDE = "create_override"
    DELETE_OVERRIDE = "delete_override"
    MODIFY_CONFIG = "modify_config"
    ROLLBACK = "rollback"


class Decision(str, Enum):
    """Authorization decision."""

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


# §11.1 Permission Matrix
PERMISSION_MATRIX: dict[Permission, dict[Role, Decision]] = {
    Permission.VIEW: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.ALLOW,
        Role.VIEWER: Decision.ALLOW,
    },
    Permission.REGISTER: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.ALLOW,
        Role.VIEWER: Decision.DENY,
    },
    Permission.TRIGGER_OPTIMIZATION: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.ALLOW,
        Role.VIEWER: Decision.DENY,
    },
    Permission.APPROVE: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.DENY,
        Role.VIEWER: Decision.DENY,
    },
    Permission.PROMOTE: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.ESCALATE,
        Role.VIEWER: Decision.DENY,
    },
    Permission.CREATE_OVERRIDE: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.DENY,
        Role.EDITOR: Decision.DENY,
        Role.VIEWER: Decision.DENY,
    },
    Permission.DELETE_OVERRIDE: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.DENY,
        Role.EDITOR: Decision.DENY,
        Role.VIEWER: Decision.DENY,
    },
    Permission.MODIFY_CONFIG: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.DENY,
        Role.VIEWER: Decision.DENY,
    },
    Permission.ROLLBACK: {
        Role.OWNER: Decision.ALLOW,
        Role.ADMIN: Decision.ALLOW,
        Role.EDITOR: Decision.DENY,
        Role.VIEWER: Decision.DENY,
    },
}


def check_permission(role: Role, permission: Permission) -> Decision:
    """Check the RBAC matrix for a role+permission combination.

    Args:
        role: User's role.
        permission: Operation being attempted.

    Returns:
        Decision: ALLOW, DENY, or ESCALATE.
    """
    perm_row = PERMISSION_MATRIX.get(permission)
    if perm_row is None:
        return Decision.DENY
    return perm_row.get(role, Decision.DENY)


def resolve_role(role_header: Optional[str]) -> Role:
    """Resolve a role string to a Role enum.

    Falls back to VIEWER for unknown/missing roles.
    """
    if not role_header:
        return Role.VIEWER
    try:
        return Role(role_header.lower())
    except ValueError:
        return Role.VIEWER


def require_permission(
    permission: Permission,
) -> Callable[..., Coroutine[None, None, Decision]]:
    """FastAPI dependency that enforces RBAC (AC-1, AC-2, AC-3).

    Extracts user role from X-User-Role header, checks against
    the permission matrix, and returns 403 for DENY.

    For ESCALATE decisions, returns the decision so the endpoint
    can create an approval task.

    Usage:
        @router.post("/endpoint")
        async def my_endpoint(
            decision: Decision = Depends(require_permission(Permission.PROMOTE))
        ):
            if decision == Decision.ESCALATE:
                # Create approval task
                ...
    """

    async def _check(
        x_user_role: str = Header(default="viewer", alias="X-User-Role"),
    ) -> Decision:
        role = resolve_role(x_user_role)
        decision = check_permission(role, permission)

        if decision == Decision.DENY:
            logger.warning(
                "RBAC denied: role=%s permission=%s",
                role.value,
                permission.value,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Permission denied: role '{role.value}' cannot "
                    f"perform '{permission.value}'"
                ),
            )

        if decision == Decision.ESCALATE:
            logger.info(
                "RBAC escalate: role=%s permission=%s — approval required",
                role.value,
                permission.value,
            )

        return decision

    return _check
