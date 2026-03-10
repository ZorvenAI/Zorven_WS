"""Skill router — selects and packages skills for each persona + prompt."""

import logging
from typing import Any

from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillRouter:
    """Selects skills for a persona and packages them for injection.

    Called by the WorkerExecutor before running the PAOR loop.
    Returns a skill_context dict merged into the agent engine context.
    """

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @property
    def skill_count(self) -> int:
        return self._registry.skill_count

    def resolve_skills_for_persona(
        self,
        persona_name: str,
        prompt: str,
        max_skills: int = 3,
    ) -> dict[str, Any]:
        """Resolve skills for a persona and return config additions.

        Returns a dict with skill_context (str) and skill_names (list).
        Returns empty dict if no skills match (fail-open).
        """
        matched = self._registry.match_skills(
            persona_name, prompt, max_skills=max_skills
        )

        if not matched:
            return {}

        skill_names = [s.meta.name for s in matched]
        mcp_tools = []
        for s in matched:
            mcp_tools.extend(s.meta.mcp_tools)

        logger.info(
            "Persona %s matched %d skill(s): %s",
            persona_name,
            len(matched),
            ", ".join(skill_names),
        )

        return {
            "worker_skill_context": self._registry.format_skill_context(matched),
            "worker_skill_names": skill_names,
            "suggested_mcp_tools": list(set(mcp_tools)),
        }
