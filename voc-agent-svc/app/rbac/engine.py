"""RBAC engine for the Voice of Customer Agent.

14-skill × 4-role permission matrix per design doc Section 11.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


# Permission matrix: skill_id → {role → permission}
_PERMISSION_MATRIX: dict[str, dict[str, Permission]] = {
    # Odoo skills — VIEWER denied
    "SKL-VoCA-01": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    "SKL-VoCA-02": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    "SKL-VoCA-03": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    # Segment Linker — all roles
    "SKL-VoCA-04": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.ALLOW,
    },
    # External research + RAG — all roles
    "SKL-VoCA-05": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.ALLOW,
    },
    "SKL-VoCA-06": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.ALLOW,
    },
    "SKL-VoCA-07": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.ALLOW,
    },
    "SKL-VoCA-08": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.ALLOW,
    },
    # Analysis skills — VIEWER denied
    "SKL-VoCA-09": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    "SKL-VoCA-10": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    "SKL-VoCA-11": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    "SKL-VoCA-12": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.DENY,
    },
    # Persister — EDITOR escalates, VIEWER denied
    "SKL-VoCA-13": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ESCALATE,
        "VIEWER": Permission.DENY,
    },
    # Escalation — all roles
    "SKL-VoCA-14": {
        "OWNER": Permission.ALLOW,
        "ADMIN": Permission.ALLOW,
        "EDITOR": Permission.ALLOW,
        "VIEWER": Permission.ALLOW,
    },
}


class RBACEngine:
    """Role-based access control for VoCA skills."""

    def check_permission(
        self, skill_id: str, user_role: str
    ) -> Permission:
        """Check if a role has permission to execute a skill."""
        role = user_role.upper()
        skill_perms = _PERMISSION_MATRIX.get(skill_id)
        if not skill_perms:
            logger.warning("Unknown skill_id in RBAC: %s", skill_id)
            return Permission.DENY
        perm = skill_perms.get(role, Permission.DENY)
        if perm == Permission.DENY:
            logger.info(
                "RBAC denied: skill=%s, role=%s", skill_id, role
            )
        elif perm == Permission.ESCALATE:
            logger.info(
                "RBAC escalation required: skill=%s, role=%s",
                skill_id,
                role,
            )
        return perm

    def is_allowed(self, skill_id: str, user_role: str) -> bool:
        """Check if a role is allowed to execute a skill."""
        return self.check_permission(skill_id, user_role) == Permission.ALLOW

    def get_allowed_skills(self, user_role: str) -> list[str]:
        """Return list of skill IDs allowed for a role."""
        return [
            sid
            for sid in _PERMISSION_MATRIX
            if self.is_allowed(sid, user_role)
        ]
