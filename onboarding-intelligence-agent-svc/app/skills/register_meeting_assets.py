"""SKL-OIA-11 — Register recordings, transcripts and captured media as BrandAssets
through the Django API.

Design §8.1 · implemented by story J-03.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-11 (register_meeting_assets) — implemented by J-03"


class RegisterMeetingAssets(BaseSkill):
    """Register recordings, transcripts and captured media as BrandAssets through the
    Django API."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
