"""SKL-OIA-13 — Record admin-edit pairs as golden-dataset candidates for the prompt
flywheel (§17.3).

Design §8.1 · implemented by story L-02.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-13 (record_golden_candidates) — implemented by L-02"


class RecordGoldenCandidates(BaseSkill):
    """Record admin-edit pairs as golden-dataset candidates for the prompt flywheel
    (§17.3)."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
