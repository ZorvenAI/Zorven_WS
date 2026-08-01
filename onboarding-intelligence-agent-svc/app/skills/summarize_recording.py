"""SKL-OIA-08 — Summarise a recording into key moments with timestamps.

Design §8.1 · implemented by story I-02.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-08 (summarize_recording) — implemented by I-02"


class SummarizeRecording(BaseSkill):
    """Summarise a recording into key moments with timestamps."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
