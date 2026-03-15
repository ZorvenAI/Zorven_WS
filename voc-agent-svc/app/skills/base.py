"""Abstract base class for all VoCA skills."""

from abc import ABC, abstractmethod
from typing import Any

from app.skills.models import SkillContext, SkillMeta, SkillResult


class BaseSkill(ABC):
    """Abstract base for all VoCA skills (SKL-VoCA-01 through SKL-VoCA-14)."""

    meta: SkillMeta  # Class variable set by each concrete skill

    @abstractmethod
    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """Execute the skill with the given input data and context."""
        ...
