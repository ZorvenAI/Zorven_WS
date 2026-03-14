"""Skill registry for TCIA."""

from app.skills.base import BaseSkill


class SkillRegistry:
    """Registry of all available TCIA skills."""

    def __init__(self) -> None:
        self._by_id: dict[str, BaseSkill] = {}
        self._by_name: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        """Register a skill by its ID and name."""
        self._by_id[skill.meta.skill_id] = skill
        self._by_name[skill.meta.name] = skill

    def get_skill(self, skill_id: str) -> BaseSkill | None:
        """Get a skill by ID or name."""
        return self._by_id.get(skill_id) or self._by_name.get(skill_id)

    def get_all_skills(self) -> dict[str, BaseSkill]:
        """Get all registered skills."""
        return dict(self._by_id)

    def skill_ids(self) -> list[str]:
        """Get all registered skill IDs."""
        return list(self._by_id.keys())

    def skills_for_role(self, role: str) -> list[BaseSkill]:
        """Get skills accessible by a given role."""
        role_upper = role.upper()
        return [
            s
            for s in self._by_id.values()
            if role_upper in [r.upper() for r in s.meta.allowed_roles]
        ]

    def skill_ids_for_role(self, role: str) -> list[str]:
        """Get skill IDs accessible by a given role."""
        return [s.meta.skill_id for s in self.skills_for_role(role)]
