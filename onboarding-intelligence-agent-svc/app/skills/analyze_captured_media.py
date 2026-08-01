"""SKL-OIA-07 — Describe and classify media captured during the meeting, including OCR.

Design §8.1 · implemented by story H-03.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-07 (analyze_captured_media) — implemented by H-03"


class AnalyzeCapturedMedia(BaseSkill):
    """Describe and classify media captured during the meeting, including OCR."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
