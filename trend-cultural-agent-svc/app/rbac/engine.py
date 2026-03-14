"""Role-based access control for TCIA skills."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class RBACAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class RBACDecision:
    """Result of an RBAC permission check."""

    def __init__(self, action: RBACAction, reason: str = "") -> None:
        self.action = action
        self.reason = reason

    @property
    def allowed(self) -> bool:
        return self.action == RBACAction.ALLOW


# Read skills accessible by all roles (VIEWER+)
_READ_SKILLS = {
    "SKL-TCIA-01",
    "SKL-TCIA-02",
    "SKL-TCIA-03",
    "SKL-TCIA-04",
    "SKL-TCIA-05",
    "SKL-TCIA-06",
    "SKL-TCIA-07",
    "SKL-TCIA-08",
    "SKL-TCIA-09",
    "SKL-TCIA-10",
    "SKL-TCIA-12",
}

# Write skills requiring EDITOR+ (escalate for EDITOR)
_WRITE_SKILLS = {"SKL-TCIA-11"}


class RBACEngine:
    """Check skill permissions based on user role."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    def check_permission(self, skill_id: str, user_role: str) -> RBACDecision:
        """Check if a user role has permission to execute a skill."""
        if not self._enabled:
            return RBACDecision(RBACAction.ALLOW, "RBAC disabled")

        role = user_role.upper()

        # OWNER/ADMIN: everything allowed
        if role in ("OWNER", "ADMIN"):
            return RBACDecision(RBACAction.ALLOW, f"{role} has full access")

        # EDITOR: read + analysis allowed, write skills escalated
        if role == "EDITOR":
            if skill_id in _READ_SKILLS:
                return RBACDecision(RBACAction.ALLOW, "EDITOR has read access")
            if skill_id in _WRITE_SKILLS:
                return RBACDecision(
                    RBACAction.ESCALATE,
                    f"EDITOR needs approval for write skill {skill_id}",
                )
            return RBACDecision(RBACAction.ALLOW, "EDITOR default allow")

        # VIEWER: read-only skills
        if role == "VIEWER":
            if skill_id in _READ_SKILLS:
                return RBACDecision(RBACAction.ALLOW, "VIEWER has read access")
            return RBACDecision(
                RBACAction.DENY,
                f"VIEWER cannot access skill {skill_id}",
            )

        return RBACDecision(RBACAction.DENY, f"Unknown role: {role}")
