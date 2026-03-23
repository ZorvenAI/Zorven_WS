"""SKL-BPA-12: Human Escalation.

Triggers escalation when:
- Insufficient WF1 data
- Low differentiation score
- No clear winner among candidates
- Cultural sensitivity flags
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HumanEscalation:
    """Evaluates escalation triggers for positioning decisions."""

    async def evaluate(
        self,
        result: dict[str, Any],
        wf1_available: bool,
    ) -> dict[str, Any]:
        """Evaluate whether human escalation is needed.

        Returns:
            Escalation assessment with triggers and recommendations.
        """
        triggers = []
        needs_escalation = False

        # Check confidence score
        confidence = result.get("confidence_score", 0.0)
        if confidence < 0.5:
            triggers.append(
                {
                    "trigger": "low_confidence",
                    "detail": f"Confidence score {confidence:.2f} below threshold",
                    "severity": "high",
                }
            )
            needs_escalation = True

        # Check WF1 data availability
        if not wf1_available:
            triggers.append(
                {
                    "trigger": "insufficient_wf1_data",
                    "detail": "No WF1 Brand Discovery data available",
                    "severity": "medium",
                }
            )

        # Check differentiation score
        diff = result.get("differentiation", {})
        diff_score = diff.get("overall_differentiation_score", 0)
        if isinstance(diff_score, (int, float)) and diff_score < 40:
            triggers.append(
                {
                    "trigger": "low_differentiation",
                    "detail": (
                        f"Differentiation score {diff_score} "
                        f"below minimum threshold"
                    ),
                    "severity": "high",
                }
            )
            needs_escalation = True

        # Check for no clear winner
        candidates = result.get("positioning_candidates", [])
        if len(candidates) >= 2:
            scores = [c.get("scores", {}).get("overall", 0) for c in candidates]
            if scores:
                sorted_scores = sorted(scores, reverse=True)
                if len(sorted_scores) >= 2:
                    margin = sorted_scores[0] - sorted_scores[1]
                    if margin < 5:
                        triggers.append(
                            {
                                "trigger": "no_clear_winner",
                                "detail": (
                                    f"Top 2 candidates within {margin:.1f} "
                                    f"points — human judgment recommended"
                                ),
                                "severity": "medium",
                            }
                        )

        return {
            "needs_escalation": needs_escalation,
            "triggers": triggers,
            "recommendation": (
                "Human review recommended before strategy implementation"
                if needs_escalation
                else "Positioning strategy ready for implementation"
            ),
        }
