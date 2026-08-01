"""SKL-OIA-15 — Fetch the pinned prompt set for a session from POI, the Redis cache, or
the fallbacks (§17.

Design §8.1 · implemented by story C-01.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-15 (fetch_prompts) — implemented by C-01"


class FetchPrompts(BaseSkill):
    """Fetch the pinned prompt set for a session from POI, the Redis cache, or the
    fallbacks (§17."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
