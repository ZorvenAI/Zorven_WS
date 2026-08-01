"""SKL-OIA-12 — Auto-generate strategy and identity drafts from the confirmed onboarding
profile.

Design §8.1 · implemented by story K-02.

Registered by A-06: the class exists and the registry resolves and
instantiates it, so the declaration in config/skills.yaml is proven to point
at something real. The body is deferred — it raises NotImplementedError
rather than returning None, so a later story cannot ship a silent no-op.
"""

from __future__ import annotations

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult

_NOT_YET = "SKL-OIA-12 (autogen_strategy_identity) — implemented by K-02"


class AutogenStrategyIdentity(BaseSkill):
    """Auto-generate strategy and identity drafts from the confirmed onboarding
    profile."""

    async def run(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError(_NOT_YET)
