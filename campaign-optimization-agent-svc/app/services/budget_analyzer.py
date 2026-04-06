"""SKL-COA-05: Budget allocation analysis.

Identifies underperformers consuming disproportionate budget,
winners that could scale, and proposes reallocation keeping
total constant (+-5% tolerance).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.meta_insights_client import CampaignInsights

logger = logging.getLogger(__name__)


@dataclass
class BudgetRecommendation:
    """Budget reallocation recommendation for a single ad set."""

    ad_set_id: str = ""
    ad_set_name: str = ""
    current_budget: float = 0.0
    proposed_budget: float = 0.0
    change_pct: float = 0.0
    reason: str = ""
    health: str = "GREEN"


@dataclass
class BudgetAnalysis:
    """Complete budget analysis for a campaign."""

    campaign_id: str = ""
    total_budget: float = 0.0
    proposed_total: float = 0.0
    balance_error_pct: float = 0.0
    recommendations: list[BudgetRecommendation] = field(
        default_factory=list
    )
    underperformers: list[str] = field(default_factory=list)
    winners: list[str] = field(default_factory=list)
    dayparting_insights: dict[str, Any] = field(default_factory=dict)


class BudgetAnalyzer:
    """Analyzes budget allocation and proposes reallocation."""

    def __init__(self):
        self._max_increase_pct = settings.MAX_DAILY_BUDGET_INCREASE_PCT
        self._max_decrease_pct = settings.MAX_DAILY_BUDGET_DECREASE_PCT
        self._roas_scale = settings.ROAS_SCALE_THRESHOLD
        self._cpa_kill_mult = settings.CPA_KILL_MULTIPLIER

    async def analyze_budget(
        self,
        campaign: Any,
        insights: CampaignInsights,
        config: dict[str, Any],
    ) -> BudgetAnalysis:
        """Analyze budget allocation and propose reallocation.

        Args:
            campaign: ActiveCampaign dataclass.
            insights: CampaignInsights from Meta API.
            config: Tenant optimization config.

        Returns:
            BudgetAnalysis with recommendations.
        """
        cpa_target = config.get("cpa_target", 50.0)
        roas_target = config.get("roas_target", 1.5)

        total_spend = insights.spend
        recs = []
        underperformers = []
        winners = []

        # Analyze each ad set's efficiency
        for ad_set in insights.ad_sets:
            current_budget = ad_set.spend
            cpa = ad_set.cost_per_action
            roas = ad_set.purchase_roas

            # Classify performance
            if cpa > cpa_target * self._cpa_kill_mult:
                # Underperformer: reduce budget
                proposed = current_budget * (
                    1 - self._max_decrease_pct / 100
                )
                recs.append(
                    BudgetRecommendation(
                        ad_set_id=ad_set.ad_set_id,
                        ad_set_name=ad_set.ad_set_name,
                        current_budget=current_budget,
                        proposed_budget=round(proposed, 2),
                        change_pct=-self._max_decrease_pct,
                        reason=(
                            f"CPA ${cpa:.2f} is "
                            f"{cpa/cpa_target:.1f}x target"
                        ),
                        health="RED",
                    )
                )
                underperformers.append(ad_set.ad_set_id)

            elif roas >= self._roas_scale:
                # Winner: increase budget
                proposed = current_budget * (
                    1 + self._max_increase_pct / 100
                )
                recs.append(
                    BudgetRecommendation(
                        ad_set_id=ad_set.ad_set_id,
                        ad_set_name=ad_set.ad_set_name,
                        current_budget=current_budget,
                        proposed_budget=round(proposed, 2),
                        change_pct=self._max_increase_pct,
                        reason=(
                            f"ROAS {roas:.2f}x exceeds "
                            f"scale threshold"
                        ),
                        health="GREEN",
                    )
                )
                winners.append(ad_set.ad_set_id)

            else:
                # Maintain current
                recs.append(
                    BudgetRecommendation(
                        ad_set_id=ad_set.ad_set_id,
                        ad_set_name=ad_set.ad_set_name,
                        current_budget=current_budget,
                        proposed_budget=current_budget,
                        change_pct=0,
                        reason="Performance within acceptable range",
                        health="YELLOW" if cpa > cpa_target else "GREEN",
                    )
                )

        # Balance check: ensure total proposed is within +-5%
        proposed_total = sum(r.proposed_budget for r in recs)
        if total_spend > 0:
            balance_error = (
                abs(proposed_total - total_spend) / total_spend * 100
            )
        else:
            balance_error = 0

        # If imbalanced, redistribute excess/deficit proportionally
        if balance_error > 5 and total_spend > 0:
            adjustment_factor = total_spend / max(proposed_total, 0.01)
            for rec in recs:
                rec.proposed_budget = round(
                    rec.proposed_budget * adjustment_factor, 2
                )
            proposed_total = sum(r.proposed_budget for r in recs)
            balance_error = (
                abs(proposed_total - total_spend) / total_spend * 100
            )

        return BudgetAnalysis(
            campaign_id=campaign.campaign_id,
            total_budget=total_spend,
            proposed_total=round(proposed_total, 2),
            balance_error_pct=round(balance_error, 1),
            recommendations=recs,
            underperformers=underperformers,
            winners=winners,
        )
