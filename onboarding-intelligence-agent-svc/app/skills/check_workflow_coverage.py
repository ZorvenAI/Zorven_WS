"""SKL-OIA-09 — Report WF1, WF2 and WF3 coverage as fractions.

Design §8.1 · implemented by story G-06.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-09 (check_workflow_coverage) — implemented by G-06"


class CheckWorkflowCoverage(BaseSkill):
    """Report WF1, WF2 and WF3 coverage as fractions."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
