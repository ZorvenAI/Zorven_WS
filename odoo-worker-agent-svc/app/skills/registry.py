"""Skill registry — indexes loaded skills for fast lookup."""

import logging

from app.skills.models import LoadedSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """In-memory index of loaded skills.

    Provides fast lookup by persona name and trigger matching against
    user prompts. Initialized once at application startup.
    """

    def __init__(self, skills: list[LoadedSkill]) -> None:
        self._skills = skills
        self._by_persona: dict[str, list[LoadedSkill]] = {}
        for skill in skills:
            for persona_id in skill.meta.target_personas:
                self._by_persona.setdefault(persona_id, []).append(skill)

        # Sort each persona's skills by priority descending
        for persona_skills in self._by_persona.values():
            persona_skills.sort(key=lambda s: s.meta.priority, reverse=True)

    @property
    def skill_count(self) -> int:
        return len(self._skills)

    def skills_for_persona(self, persona_name: str) -> list[LoadedSkill]:
        """Return all skills that target the given persona, sorted by priority."""
        return self._by_persona.get(persona_name, [])

    def match_skills(
        self,
        persona_name: str,
        prompt: str,
        max_skills: int = 3,
        max_total_tokens: int = 1500,
    ) -> list[LoadedSkill]:
        """Match skills for a persona based on trigger phrases in the prompt.

        Returns up to max_skills whose triggers appear in prompt,
        respecting max_total_tokens budget. Returns [] on no match (fail-open).
        """
        persona_skills = self.skills_for_persona(persona_name)
        if not persona_skills:
            return []

        prompt_lower = prompt.lower()
        matched: list[LoadedSkill] = []
        total_tokens = 0

        for skill in persona_skills:
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
