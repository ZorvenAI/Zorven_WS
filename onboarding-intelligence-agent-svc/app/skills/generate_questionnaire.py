"""SKL-OIA-02 — Generate a questionnaire to the operator's requested count and depth.

Design §8.1 · implemented by story C-03.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-02 (generate_questionnaire) — implemented by C-03"


class GenerateQuestionnaire(BaseSkill):
    """Generate a questionnaire to the operator's requested count and depth."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
