"""SKL-NTA-14: Human escalation evaluation for low-confidence decisions."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class HumanEscalation:
    """Evaluate escalation triggers for naming decisions."""

    async def evaluate(
        self, confidence_score: float, strategy: dict[str, Any]
    ) -> dict[str, Any]:
        """Check if human review is needed."""
        triggers = []

        if confidence_score < settings.CONFIDENCE_THRESHOLD:
            triggers.append(
                {
                    "trigger": "low_confidence",
                    "threshold": settings.CONFIDENCE_THRESHOLD,
                    "actual": confidence_score,
                }
            )

        return {
            "escalation_needed": len(triggers) > 0,
            "triggers": triggers,
        }
