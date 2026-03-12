"""RBAC engine - role-based access control for CIA skills.

Permission matrix per the design document:
- VIEWER: read-only skills (search, profiling, reviews, pricing, market share, RAG)
- EDITOR: adds SWOT, positioning, benchmarking; ESCALATE on persist/report
- ADMIN/OWNER: full access (same as EDITOR plus persist without escalation)
"""

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Design-document permission matrix for 12 CIA skills
RBAC_MATRIX: dict[str, list[str]] = {
    "SKL-CIA-01": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # competitor discovery
    "SKL-CIA-02": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # website profiler
    "SKL-CIA-03": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # social analyzer
    "SKL-CIA-04": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # review aggregator
    "SKL-CIA-05": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # pricing extractor
    "SKL-CIA-06": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # market share estimator
    "SKL-CIA-07": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # RAG retrieval
    "SKL-CIA-08": ["OWNER", "ADMIN", "EDITOR"],  # SWOT generator
    "SKL-CIA-09": ["OWNER", "ADMIN", "EDITOR"],  # positioning gap analyzer
    "SKL-CIA-10": ["OWNER", "ADMIN", "EDITOR"],  # benchmarking synthesizer
    "SKL-CIA-11": ["OWNER", "ADMIN", "EDITOR"],  # report persister
    "SKL-CIA-12": ["OWNER", "ADMIN", "EDITOR", "VIEWER"],  # human escalation
}

# Skills that require ESCALATE for EDITOR role
ESCALATE_FOR_EDITOR: set[str] = {"SKL-CIA-11"}


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

        if user_role not in allowed_roles:
            return RBACDecision(
                skill_id=skill_id,
                role=user_role,
                decision="DENY",
                reason=f"Role {user_role} not in allowed roles {allowed_roles}",
            )

        # EDITOR escalation for write skills
        if user_role == "EDITOR" and skill_id in ESCALATE_FOR_EDITOR:
            return RBACDecision(
                skill_id=skill_id,
                role=user_role,
                decision="ESCALATE",
                reason=f"EDITOR role requires approval for {skill_id}",
            )

        return RBACDecision(
            skill_id=skill_id,
            role=user_role,
            decision="ALLOW",
            reason=f"Role {user_role} permitted for {skill_id}",
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
        return skill_id in {"SKL-CIA-11"}
