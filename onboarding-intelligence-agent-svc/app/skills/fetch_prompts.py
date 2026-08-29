"""SKL-OIA-15 — Resolve and pin prompt versions for this session.

Design §8.3, §17.2 · implemented by story L-01.

Wraps ``PromptLoader.resolve_for_session`` in the skill contract so the
resolution can be invoked through the registry (and therefore through the
guardrail chain) like any other skill.
"""

from __future__ import annotations

from typing import Any

from app.prompts.loader import PromptLoader
from app.prompts.mapping import (
    ALL_PROMPT_IDS,
    LIVE_PROMPTS,
    PREP_PROMPTS,
    PROCESS_PROMPTS,
)
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult


class FetchPrompts(BaseSkill):
    """Resolve and pin all prompts for this session's mode."""

    def __init__(
        self,
        meta: Any,
        *,
        prompt_loader: PromptLoader | None = None,
        **_kwargs: object,
    ) -> None:
        super().__init__(meta)
        self._loader = prompt_loader

    async def run(self, context: SkillContext) -> SkillResult:
        if self._loader is None:
            return SkillResult(
                skill_id="SKL-OIA-15",
                output={
                    "prompt_versions": {},
                    "templates": {},
                    "degraded": True,
                },
            )

        mode = context.input_context.get("mode", "PREP")
        tenant_id = context.tenant_context.tenant_id

        prompt_set = {
            "PREP": PREP_PROMPTS,
            "LIVE": LIVE_PROMPTS,
            "PROCESS": PROCESS_PROMPTS,
        }.get(mode, ALL_PROMPT_IDS)

        resolved, degraded = await self._loader.resolve_for_session(
            prompt_set, tenant_id
        )

        versions = {pid: r.version for pid, r in resolved.items()}
        templates = {pid: r.template for pid, r in resolved.items()}

        return SkillResult(
            skill_id="SKL-OIA-15",
            output={
                "prompt_versions": versions,
                "templates": templates,
                "degraded": degraded,
            },
        )
