"""SKL-CGA-14: Human Escalation.

Evaluates whether creative generation results need human review
based on confidence thresholds, image generation failures,
compliance violations, and image-copy coherence scores.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class HumanEscalation:
    """Evaluates whether creative results need human review."""

    def check(
        self,
        result: dict[str, Any],
        threshold: float = 0.7,
    ) -> dict[str, Any]:
        """Check if human escalation is needed.

        Escalates when:
        - confidence_score < threshold
        - Image generation failed (total_images == 0 or high fail rate)
        - Compliance violations > 20%
        - Image-copy coherence average < 50

        Args:
            result: Complete CampaignCreativePackage dict.
            threshold: Confidence threshold for escalation (default 0.7).

        Returns:
            Dict with escalate (bool) and reasons (list[str]).
        """
        reasons: list[str] = []

        # 1. Confidence check
        confidence = result.get("confidence_score", 0.0)
        if confidence < threshold:
            reasons.append(
                f"Confidence score {confidence:.2f} is below "
                f"threshold {threshold:.2f}"
            )

        # 2. Image generation failures
        total_images = result.get("total_images_generated", 0)
        if total_images == 0:
            reasons.append(
                "No images were generated — image generation "
                "completely failed"
            )

        # 3. Compliance violations > 20%
        compliance_rate = result.get("compliance_pass_rate", 1.0)
        if compliance_rate < 0.8:
            violation_pct = (1.0 - compliance_rate) * 100
            reasons.append(
                f"Compliance violation rate {violation_pct:.1f}% "
                f"exceeds 20% threshold"
            )

        # 4. Image-copy coherence average < 50
        coherence_avg = self._calc_coherence_average(result)
        if coherence_avg is not None and coherence_avg < 50:
            reasons.append(
                f"Average image-copy coherence {coherence_avg:.1f} "
                f"is below minimum threshold of 50"
            )

        escalate = len(reasons) > 0

        if escalate:
            logger.warning(
                "Human escalation triggered with %d reason(s): %s",
                len(reasons),
                "; ".join(reasons),
            )
        else:
            logger.info(
                "No escalation needed — confidence %.2f, "
                "compliance %.1f%%, coherence avg %.1f",
                confidence,
                compliance_rate * 100,
                coherence_avg if coherence_avg is not None else 0,
            )

        return {
            "escalate": escalate,
            "reasons": reasons,
        }

    def _calc_coherence_average(
        self, result: dict[str, Any]
    ) -> float | None:
        """Calculate average image-copy coherence across all units.

        Args:
            result: CampaignCreativePackage dict.

        Returns:
            Average coherence score, or None if no units found.
        """
        scores: list[float] = []

        for pkg in result.get("ad_set_packages", []):
            for unit in pkg.get("creative_units", []):
                coherence = unit.get("image_copy_coherence")
                if coherence is not None:
                    try:
                        scores.append(float(coherence))
                    except (ValueError, TypeError):
                        continue

        if not scores:
            return None

        return sum(scores) / len(scores)
