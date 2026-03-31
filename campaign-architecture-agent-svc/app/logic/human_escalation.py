"""SKL-CAA-12: Human Escalation.

Triggers human review when:
- Confidence < threshold (default 0.7)
- Unrealistic KPI targets (vs benchmarks)
- Budget issues (too low, too high)
- Special Ad Category uncertainty (housing/employment/credit)
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class HumanEscalation:
    """Check campaign blueprint for escalation triggers."""

    def check(
        self,
        result: dict[str, Any],
        benchmarks: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check result for escalation triggers.

        Returns dict with should_escalate bool and reasons list.
        """
        reasons: list[str] = []

        # Confidence threshold
        confidence = result.get("confidence_score", 0.0)
        if confidence < settings.CONFIDENCE_THRESHOLD:
            reasons.append(
                f"Low confidence score: {confidence:.2f} "
                f"(threshold: {settings.CONFIDENCE_THRESHOLD})"
            )

        # Budget sanity
        blueprint = result.get("blueprint", {})
        daily_budget = blueprint.get("daily_budget", 0)
        if daily_budget > 0:
            if daily_budget < settings.MIN_DAILY_BUDGET:
                reasons.append(
                    f"Budget ${daily_budget:.2f}/day below "
                    f"Meta minimum (${settings.MIN_DAILY_BUDGET})"
                )
            if daily_budget > settings.DEFAULT_DAILY_BUDGET_CAP:
                reasons.append(
                    f"Budget ${daily_budget:.2f}/day exceeds "
                    f"cap (${settings.DEFAULT_DAILY_BUDGET_CAP})"
                )

        # Special Ad Category uncertainty
        special_cat = result.get("special_ad_category", "")
        if special_cat and special_cat != "NONE":
            reasons.append(
                f"Special Ad Category detected: {special_cat}. "
                f"Manual review required for compliance."
            )

        # KPI realism check
        kpi_targets = result.get("kpi_targets", {})
        if kpi_targets and benchmarks:
            bm = benchmarks.get("benchmarks", {})
            per_funnel = kpi_targets.get("targets", {})
            for stage, kpis in per_funnel.items():
                roas_target = kpis.get("roas", 0)
                roas_high = bm.get("roas", {}).get("high", 8.0)
                if roas_target > roas_high * 1.5:
                    reasons.append(
                        f"Unrealistic ROAS target for {stage}: "
                        f"{roas_target:.1f} "
                        f"(industry high: {roas_high:.1f})"
                    )

        should_escalate = len(reasons) > 0
        if should_escalate:
            logger.warning(
                "Human escalation triggered: %s",
                "; ".join(reasons),
            )

        return {
            "should_escalate": should_escalate,
            "reasons": reasons,
            "confidence_score": confidence,
        }
