"""SKL-BSA-14: Confidence threshold check for human review."""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class HumanEscalation:
    """Evaluates whether narrative results need human review."""

    async def evaluate(
        self,
        confidence: float,
        validation_issues: dict[str, Any],
    ) -> dict[str, Any]:
        """Check if escalation is needed."""
        threshold = settings.CONFIDENCE_THRESHOLD
        reasons = []

        if confidence < threshold:
            reasons.append(
                f"Confidence {confidence:.2f} below threshold {threshold}"
            )

        issues = validation_issues.get("issues", [])
        if len(issues) > 3:
            reasons.append(f"Multiple validation issues ({len(issues)})")

        escalation_needed = len(reasons) > 0

        if escalation_needed:
            logger.warning(
                "Human escalation triggered: %s",
                "; ".join(reasons),
            )

        return {
            "escalation_needed": escalation_needed,
            "reasons": reasons,
            "confidence": confidence,
            "threshold": threshold,
        }
