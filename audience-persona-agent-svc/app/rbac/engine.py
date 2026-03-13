"""RBAC engine for the Audience Persona Agent.

Permission matrix for 14 APA skills:
- SKL-APA-01..05 (research): ALL roles
- SKL-APA-05b (Odoo Survey): OWNER/ADMIN/EDITOR only
- SKL-APA-05c (Odoo CRM): OWNER/ADMIN/EDITOR only
- SKL-APA-06 (RAG): ALL roles
- SKL-APA-07..10 (LLM analysis): OWNER/ADMIN/EDITOR only
- SKL-APA-11 (Persist): OWNER/ADMIN (ESCALATE for EDITOR)
- SKL-APA-12 (Escalation): ALL roles
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RBACAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class RBACDecision:
    """Result of an RBAC check."""

    def __init__(self, action: RBACAction, reason: str = "") -> None:
        self.action = action
        self.reason = reason

    @property
    def allowed(self) -> bool:
        return self.action == RBACAction.ALLOW


# Read skills accessible by all roles including VIEWER
_READ_SKILLS_ALL = {
    "SKL-APA-01",
    "SKL-APA-02",
    "SKL-APA-03",
    "SKL-APA-04",
    "SKL-APA-05",
    "SKL-APA-06",
    "SKL-APA-12",
}

# Skills requiring EDITOR or above (no VIEWER)
_EDITOR_PLUS_SKILLS = {
    "SKL-APA-05b",
    "SKL-APA-05c",
    "SKL-APA-07",
    "SKL-APA-08",
    "SKL-APA-09",
    "SKL-APA-10",
}

# Write skill requiring ESCALATE for EDITOR
_WRITE_SKILLS = {"SKL-APA-11"}

# All valid skill IDs
_ALL_SKILLS = _READ_SKILLS_ALL | _EDITOR_PLUS_SKILLS | _WRITE_SKILLS


class RBACEngine:
    """Role-based access control for APA skills."""

    def check_permission(self, skill_id: str, user_role: str) -> RBACDecision:
        """Check if a role can execute a skill."""
        role = user_role.upper()

        if skill_id not in _ALL_SKILLS:
            return RBACDecision(
                RBACAction.DENY,
                f"Unknown skill: {skill_id}",
            )

        # OWNER and ADMIN can do everything
        if role in ("OWNER", "ADMIN"):
            return RBACDecision(RBACAction.ALLOW)

        # EDITOR
        if role == "EDITOR":
            if skill_id in _READ_SKILLS_ALL:
                return RBACDecision(RBACAction.ALLOW)
            if skill_id in _EDITOR_PLUS_SKILLS:
                return RBACDecision(RBACAction.ALLOW)
            if skill_id in _WRITE_SKILLS:
                return RBACDecision(
                    RBACAction.ESCALATE,
                    f"EDITOR requires admin approval for {skill_id}",
                )
            return RBACDecision(
                RBACAction.DENY,
                f"EDITOR cannot access {skill_id}",
            )

        # VIEWER
        if role == "VIEWER":
            if skill_id in _READ_SKILLS_ALL:
                return RBACDecision(RBACAction.ALLOW)
            return RBACDecision(
                RBACAction.DENY,
                f"VIEWER cannot access {skill_id}",
            )

        # Unknown role
        return RBACDecision(
            RBACAction.DENY,
            f"Unknown role: {role}",
        )

    @staticmethod
    def is_write_skill(skill_id: str) -> bool:
        """Check if a skill is a write skill."""
        return skill_id in _WRITE_SKILLS

    @staticmethod
    def skills_for_role(role: str) -> set[str]:
        """Return the set of skill IDs accessible by a role."""
        role = role.upper()
        if role in ("OWNER", "ADMIN"):
            return set(_ALL_SKILLS)
        if role == "EDITOR":
            return _READ_SKILLS_ALL | _EDITOR_PLUS_SKILLS | _WRITE_SKILLS
        if role == "VIEWER":
            return set(_READ_SKILLS_ALL)
        return set()
