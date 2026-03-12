"""Skill registry — central lookup for all 8 MRA skills."""

import logging

from app.skills.base import BaseSkill

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registers and provides lookup for all MRA skills."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._by_name: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill instance."""
        self._skills[skill.meta.skill_id] = skill
        self._by_name[skill.meta.name] = skill
        logger.info("Registered skill %s (%s)", skill.meta.skill_id, skill.meta.name)

    def get_skill(self, skill_id: str) -> BaseSkill | None:
        """Look up a skill by ID (e.g. 'SKL-MRA-01') or name."""
        return self._skills.get(skill_id) or self._by_name.get(skill_id)

    def get_all_skills(self) -> list[BaseSkill]:
        """Return all registered skills."""
        return list(self._skills.values())

    def skill_ids(self) -> list[str]:
        """Return all registered skill IDs."""
        return list(self._skills.keys())

    def skills_for_role(self, role: str) -> list[BaseSkill]:
        """Return skills accessible to the given role."""
        return [s for s in self._skills.values() if role in s.meta.allowed_roles]

    def skill_ids_for_role(self, role: str) -> list[str]:
        """Return skill IDs accessible to the given role."""
        return [s.meta.skill_id for s in self.skills_for_role(role)]
