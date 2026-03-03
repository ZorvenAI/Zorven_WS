"""Skill registry — indexes loaded skills for fast lookup."""

import logging

from app.skills.models import LoadedSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """In-memory index of loaded skills.

    Provides fast lookup by agent ID and trigger matching against
    user prompts.  Initialized once at application startup.
    """

    def __init__(self, skills: list[LoadedSkill]) -> None:
        self._skills = skills
        self._by_agent: dict[str, list[LoadedSkill]] = {}
        for skill in skills:
            for agent_id in skill.meta.target_agents:
                self._by_agent.setdefault(agent_id, []).append(skill)

        for agent_skills in self._by_agent.values():
            agent_skills.sort(key=lambda s: s.meta.priority, reverse=True)

    @property
    def skill_count(self) -> int:
        return len(self._skills)

    def skills_for_agent(self, agent_id: str) -> list[LoadedSkill]:
        """Return all skills that target the given agent, sorted by priority."""
        return self._by_agent.get(agent_id, [])

    def match_skills(
        self,
        agent_id: str,
        prompt: str,
        max_skills: int = 3,
        max_total_tokens: int = 1500,
    ) -> list[LoadedSkill]:
        """Match skills for an agent based on trigger phrases in the prompt.

        Returns up to *max_skills* whose triggers appear in *prompt*,
        respecting *max_total_tokens*.  Skills are returned in priority
        order.  Returns empty list when nothing matches (fail-open).
        """
        agent_skills = self.skills_for_agent(agent_id)
        if not agent_skills:
            return []

        prompt_lower = prompt.lower()
        matched: list[LoadedSkill] = []
        total_tokens = 0

        for skill in agent_skills:
            if len(matched) >= max_skills:
                break
            if total_tokens + skill.meta.max_tokens > max_total_tokens:
                continue
            if self._triggers_match(skill, prompt_lower):
                matched.append(skill)
                total_tokens += skill.meta.max_tokens

        return matched

    @staticmethod
    def _triggers_match(skill: LoadedSkill, prompt_lower: str) -> bool:
        """Check if any of the skill's triggers match the prompt."""
        for trigger in skill.meta.triggers:
            if trigger.lower() in prompt_lower:
                return True
        return False

    @staticmethod
    def format_skill_context(skills: list[LoadedSkill]) -> str:
        """Format matched skills into a single string for prompt injection."""
        if not skills:
            return ""

        parts = ["## Additional Skill Context\n"]
        for skill in skills:
            parts.append(f"### {skill.meta.description}\n")
            parts.append(skill.body)
            parts.append("")

        return "\n".join(parts)
