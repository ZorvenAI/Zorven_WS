"""Abstract base skill that all MRA skills extend."""

from abc import ABC, abstractmethod

from app.skills.models import SkillContext, SkillMeta, SkillResult


class BaseSkill(ABC):
    """Abstract base class for executable skills."""

    meta: SkillMeta

    @abstractmethod
    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """Execute the skill and return a result."""
        ...
