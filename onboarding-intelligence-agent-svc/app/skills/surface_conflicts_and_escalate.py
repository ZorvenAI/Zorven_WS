"""SKL-OIA-14 — Surface conflicting evidence for a field and escalate for human
resolution.

Design §8.3 · implemented by story J-05.

Builds escalation payloads from detected field conflicts. The PROCESS pipeline
calls ``_handle_conflicts`` directly; this skill provides the standalone
invocation path through the SkillRegistry for LIVE/EDITOR use where the
IG → RBAC → PG → OG chain must run.
"""

from __future__ import annotations

from typing import Any

from app.logic.conflict_helpers import build_candidates
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult


class SurfaceConflictsAndEscalate(BaseSkill):
    """Surface conflicting evidence for a field and escalate for human resolution."""

    async def run(self, context: SkillContext) -> SkillResult:
        conflicts = context.input_context.get("conflicts", [])

        if not conflicts:
            return SkillResult(
                skill_id=self.meta.skill_id,
                output={
                    "escalation_count": 0,
                    "items": [],
                },
            )

        items: list[dict[str, Any]] = []
        for c in conflicts:
            candidates = build_candidates(c)
            items.append(
                {
                    "field_name": c.get("field_name"),
                    "reason_code": "FIELD_CONFLICT",
                    "candidate_count": len(candidates),
                }
            )

        return SkillResult(
            skill_id=self.meta.skill_id,
            output={
                "escalation_count": len(items),
                "severity": "HIGH" if len(items) > 2 else "MEDIUM",
                "items": items,
            },
        )
