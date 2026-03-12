"""RBAC engine — role-based access control for MRA skills.

Permission matrix per the design document:
- VIEWER: read-only skills (search, lookup, retrieval, escalation)
- EDITOR: adds synthesis, report generation, RAG indexing
- ADMIN/OWNER: full access (same as EDITOR for MRA)
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Design-document permission matrix
RBAC_MATRIX: dict[str, list[str]] = {
    "SKL-MRA-01": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # web search
    "SKL-MRA-02": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # data extraction
    "SKL-MRA-03": ["OWNER", "ADMIN", "EDITOR"],  # analysis synthesis
    "SKL-MRA-04": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # economic lookup
    "SKL-MRA-05": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # RAG retrieval
    "SKL-MRA-06": ["OWNER", "ADMIN", "EDITOR"],  # report generation
    "SKL-MRA-07": ["OWNER", "ADMIN", "EDITOR"],  # RAG indexing
    "SKL-MRA-08": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # escalation
}


class RBACDecision(BaseModel):
    """Result of an RBAC permission check."""

    skill_id: str
    role: str
    decision: str = Field(..., description="ALLOW, DENY, or ESCALATE")
    reason: str = ""


class RBACEngine:
    """Enforces role-based access control on skill invocations."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def check_permission(self, skill_id: str, user_role: str) -> RBACDecision:
        """Check if a role is allowed to invoke a skill."""
        if not self.enabled:
            return RBACDecision(
                skill_id=skill_id,
                role=user_role,
                decision="ALLOW",
                reason="RBAC disabled",
            )

        allowed_roles = RBAC_MATRIX.get(skill_id)
        if allowed_roles is None:
            return RBACDecision(
                skill_id=skill_id,
                role=user_role,
                decision="DENY",
                reason=f"Unknown skill: {skill_id}",
            )

        if user_role in allowed_roles:
            return RBACDecision(
                skill_id=skill_id,
                role=user_role,
                decision="ALLOW",
                reason=f"Role {user_role} permitted for {skill_id}",
            )

        return RBACDecision(
            skill_id=skill_id,
            role=user_role,
            decision="DENY",
            reason=f"Role {user_role} not in allowed roles {allowed_roles}",
        )

    def get_allowed_skills(self, user_role: str) -> list[str]:
        """Return skill IDs the role can access."""
        if not self.enabled:
            return list(RBAC_MATRIX.keys())

        return [
            skill_id for skill_id, roles in RBAC_MATRIX.items() if user_role in roles
        ]

    def is_write_skill(self, skill_id: str) -> bool:
        """Check if a skill performs write operations (PG-03)."""
        return skill_id in {"SKL-MRA-06", "SKL-MRA-07"}
