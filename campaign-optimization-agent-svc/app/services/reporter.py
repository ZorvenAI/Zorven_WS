"""SKL-COA-13: Performance report generation.

Generates performance reports using Claude for narrative summaries.
Falls back to structured data if LLM circuit breaker is open.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.logic.circuit_breaker import get_breaker
from app.prompts.fallbacks import FALLBACK_REPORTER
from app.services.anthropic_client import AnthropicClient
from app.services.meta_insights_client import CampaignInsights
from app.services.performance_analyzer import CampaignAnalysis

logger = logging.getLogger(__name__)


@dataclass
class PerformanceReport:
    """Generated performance report."""

    campaign_id: str = ""
    campaign_name: str = ""
    overall_health: str = ""
    narrative: str = ""
    key_metrics: dict[str, Any] = field(default_factory=dict)
    top_performers: list[dict[str, Any]] = field(default_factory=list)
    bottom_performers: list[dict[str, Any]] = field(default_factory=list)
    trends: dict[str, Any] = field(default_factory=dict)
    recommendations_summary: list[str] = field(default_factory=list)


class Reporter:
    """Generates performance reports with optional LLM narratives."""

    def __init__(
        self,
        llm_client: AnthropicClient | None = None,
        prompt_loader: Any = None,
    ):
        self._llm = llm_client
        self._breaker = get_breaker("llm")
        self._prompt_loader = prompt_loader

    async def generate_report(
        self,
        campaign: Any,
        insights: CampaignInsights,
        analysis: CampaignAnalysis,
    ) -> PerformanceReport:
        """Generate a performance report for a campaign.

        Args:
            campaign: ActiveCampaign dataclass.
            insights: CampaignInsights from Meta API.
            analysis: CampaignAnalysis results.

        Returns:
            PerformanceReport with narrative and structured data.
        """
        # Build key metrics
        key_metrics = {
            "impressions": insights.impressions,
            "clicks": insights.clicks,
            "spend": insights.spend,
            "ctr": insights.ctr,
            "cpm": insights.cpm,
            "frequency": insights.frequency,
            "reach": insights.reach,
            "conversions": insights.conversions,
            "cpa": insights.cost_per_action,
            "roas": insights.purchase_roas,
        }

        # Identify top/bottom performers
        sorted_sets = sorted(
            analysis.ad_set_analyses,
            key=lambda x: x.roas_actual,
            reverse=True,
        )
        top = [
            {
                "ad_set_id": a.ad_set_id,
                "ad_set_name": a.ad_set_name,
                "roas": a.roas_actual,
                "cpa": a.cpa_actual,
                "health": a.overall_health,
            }
            for a in sorted_sets[:3]
        ]
        bottom = [
            {
                "ad_set_id": a.ad_set_id,
                "ad_set_name": a.ad_set_name,
                "roas": a.roas_actual,
                "cpa": a.cpa_actual,
                "health": a.overall_health,
            }
            for a in sorted_sets[-3:]
        ]

        # Collect recommendations
        rec_summary = []
        for a in analysis.ad_set_analyses:
            rec_summary.extend(a.recommendations)

        # Generate narrative
        narrative = ""
        if self._llm and not self._breaker.is_open:
            try:
                narrative = await self._generate_narrative(
                    campaign, insights, analysis, key_metrics, top, bottom
                )
                self._breaker.record_success()
            except Exception as exc:
                self._breaker.record_failure()
                logger.error(
                    "Report narrative generation failed (%s): %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )

        if not narrative:
            # Fallback to structured summary
            narrative = (
                f"Campaign '{campaign.campaign_name}' health: "
                f"{analysis.overall_health}. "
                f"Spend: ${insights.spend:.2f}, "
                f"CTR: {insights.ctr:.2f}%, "
                f"ROAS: {insights.purchase_roas:.2f}x. "
                f"{analysis.red_count} ad sets RED, "
                f"{analysis.yellow_count} YELLOW, "
                f"{analysis.green_count} GREEN."
            )

        return PerformanceReport(
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            overall_health=analysis.overall_health,
            narrative=narrative,
            key_metrics=key_metrics,
            top_performers=top,
            bottom_performers=bottom,
            recommendations_summary=rec_summary,
        )

    async def _generate_narrative(
        self,
        campaign: Any,
        insights: CampaignInsights,
        analysis: CampaignAnalysis,
        metrics: dict[str, Any],
        top: list[dict],
        bottom: list[dict],
    ) -> str:
        """Generate an LLM narrative report."""
        if self._prompt_loader is not None:
            system = await self._prompt_loader.load(
                "zorven-wf3-coa-reporter",
                fallback=FALLBACK_REPORTER,
            )
        else:
            system = FALLBACK_REPORTER
        user = (
            f"Campaign: {campaign.campaign_name}\n"
            f"Health: {analysis.overall_health}\n"
            f"Metrics: spend=${metrics['spend']:.2f}, "
            f"CTR={metrics['ctr']:.2f}%, "
            f"CPA=${metrics['cpa']:.2f}, "
            f"ROAS={metrics['roas']:.2f}x, "
            f"frequency={metrics['frequency']:.1f}\n"
            f"Top performers: {top}\n"
            f"Bottom performers: {bottom}\n"
            f"Red/Yellow/Green: "
            f"{analysis.red_count}/{analysis.yellow_count}/"
            f"{analysis.green_count}\n"
        )
        return await self._llm.generate(system, user)
