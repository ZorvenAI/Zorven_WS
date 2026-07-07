"""SKL-COA-03: Core performance analysis engine.

Analyzes campaign metrics: CPA vs target, ROAS vs target,
CTR trends, frequency, spend pacing. Returns per-ad-set health analysis.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.anthropic_client import AnthropicClient
from app.services.meta_insights_client import CampaignInsights

logger = logging.getLogger(__name__)


@dataclass
class AdSetAnalysis:
    """Analysis result for a single ad set."""

    ad_set_id: str = ""
    ad_set_name: str = ""
    cpa_status: str = "OK"  # KILL, SCALE, OK
    cpa_actual: float = 0.0
    cpa_target: float = 0.0
    roas_status: str = "OK"  # KILL, SCALE, OK
    roas_actual: float = 0.0
    roas_target: float = 0.0
    ctr_trend: str = "STABLE"  # FATIGUE, STABLE, IMPROVING
    ctr_current: float = 0.0
    ctr_peak: float = 0.0
    frequency_status: str = "OK"  # HIGH, OK
    frequency: float = 0.0
    pacing_status: str = "OK"  # OVERSPENDING, UNDERSPENDING, OK
    spend_pct: float = 0.0
    overall_health: str = "GREEN"  # RED, YELLOW, GREEN
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CampaignAnalysis:
    """Complete analysis result for a campaign."""

    campaign_id: str = ""
    overall_health: str = "GREEN"  # RED, YELLOW, GREEN
    ad_set_analyses: list[AdSetAnalysis] = field(default_factory=list)
    narrative: str = ""
    red_count: int = 0
    yellow_count: int = 0
    green_count: int = 0


class PerformanceAnalyzer:
    """Core analysis engine for campaign optimization."""

    def __init__(self, llm_client: AnthropicClient | None = None):
        self._llm = llm_client

    async def analyze_campaign(
        self,
        campaign: Any,
        insights: CampaignInsights,
        config: dict[str, Any],
    ) -> CampaignAnalysis:
        """Analyze a campaign's performance.

        Args:
            campaign: ActiveCampaign dataclass.
            insights: CampaignInsights from Meta Insights API.
            config: Tenant optimization config.

        Returns:
            CampaignAnalysis with per-ad-set breakdowns.
        """
        cpa_target = config.get("cpa_target", 50.0)
        roas_target = config.get("roas_target", 1.5)
        cpa_kill_mult = settings.CPA_KILL_MULTIPLIER
        roas_scale_thresh = settings.ROAS_SCALE_THRESHOLD

        ad_set_analyses = []
        for ad_set in insights.ad_sets:
            analysis = self._analyze_ad_set(
                ad_set=ad_set,
                cpa_target=cpa_target,
                roas_target=roas_target,
                cpa_kill_mult=cpa_kill_mult,
                roas_scale_thresh=roas_scale_thresh,
                total_spend=insights.spend,
            )
            ad_set_analyses.append(analysis)

        # Aggregate health
        red = sum(1 for a in ad_set_analyses if a.overall_health == "RED")
        yellow = sum(1 for a in ad_set_analyses if a.overall_health == "YELLOW")
        green = sum(1 for a in ad_set_analyses if a.overall_health == "GREEN")

        if red > len(ad_set_analyses) * 0.5:
            overall = "RED"
        elif red > 0 or yellow > len(ad_set_analyses) * 0.3:
            overall = "YELLOW"
        else:
            overall = "GREEN"

        # Generate narrative via LLM (optional, degrades gracefully)
        narrative = ""
        if self._llm:
            try:
                narrative = await self._generate_narrative(
                    campaign, insights, ad_set_analyses, overall
                )
            except Exception as exc:
                logger.error(
                    "Narrative generation failed (%s): %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )

        return CampaignAnalysis(
            campaign_id=campaign.campaign_id,
            overall_health=overall,
            ad_set_analyses=ad_set_analyses,
            narrative=narrative,
            red_count=red,
            yellow_count=yellow,
            green_count=green,
        )

    def _analyze_ad_set(
        self,
        ad_set: Any,
        cpa_target: float,
        roas_target: float,
        cpa_kill_mult: float,
        roas_scale_thresh: float,
        total_spend: float,
    ) -> AdSetAnalysis:
        """Analyze a single ad set's performance."""
        recommendations = []

        # CPA analysis
        cpa = ad_set.cost_per_action if ad_set.cost_per_action > 0 else 0
        if cpa > cpa_target * cpa_kill_mult:
            cpa_status = "KILL"
            recommendations.append(
                f"CPA ${cpa:.2f} is {cpa/cpa_target:.1f}x target "
                f"(${cpa_target:.2f}). Consider pausing."
            )
        elif cpa < cpa_target * 0.7:
            cpa_status = "SCALE"
            recommendations.append(
                f"CPA ${cpa:.2f} is well below target. Consider scaling."
            )
        else:
            cpa_status = "OK"

        # ROAS analysis
        roas = ad_set.purchase_roas
        if roas > 0 and roas < roas_target * 0.5:
            roas_status = "KILL"
            recommendations.append(
                f"ROAS {roas:.2f}x is far below target "
                f"({roas_target:.2f}x). Consider pausing."
            )
        elif roas >= roas_scale_thresh:
            roas_status = "SCALE"
            recommendations.append(
                f"ROAS {roas:.2f}x exceeds scale threshold. "
                f"Consider increasing budget."
            )
        else:
            roas_status = "OK"

        # CTR trend (simplified without history; fatigue_detector
        # handles detailed analysis)
        ctr = ad_set.ctr
        ctr_trend = "STABLE"

        # Frequency analysis
        frequency = ad_set.frequency
        freq_status = "HIGH" if frequency > 3.0 else "OK"
        if frequency > 3.0:
            recommendations.append(
                f"Frequency {frequency:.1f} is high. " f"Consider creative refresh."
            )

        # Spend pacing
        spend_pct = (ad_set.spend / total_spend * 100) if total_spend > 0 else 0
        if spend_pct > 60:
            pacing_status = "OVERSPENDING"
            recommendations.append(f"Ad set consuming {spend_pct:.0f}% of total spend.")
        elif spend_pct < 10 and len(recommendations) == 0:
            pacing_status = "UNDERSPENDING"
        else:
            pacing_status = "OK"

        # Overall health
        if cpa_status == "KILL" or roas_status == "KILL":
            health = "RED"
        elif (
            freq_status == "HIGH"
            or pacing_status == "OVERSPENDING"
            or ctr_trend == "FATIGUE"
        ):
            health = "YELLOW"
        else:
            health = "GREEN"

        return AdSetAnalysis(
            ad_set_id=ad_set.ad_set_id,
            ad_set_name=ad_set.ad_set_name,
            cpa_status=cpa_status,
            cpa_actual=cpa,
            cpa_target=cpa_target,
            roas_status=roas_status,
            roas_actual=roas,
            roas_target=roas_target,
            ctr_trend=ctr_trend,
            ctr_current=ctr,
            frequency_status=freq_status,
            frequency=frequency,
            pacing_status=pacing_status,
            spend_pct=spend_pct,
            overall_health=health,
            recommendations=recommendations,
        )

    async def _generate_narrative(
        self,
        campaign: Any,
        insights: CampaignInsights,
        analyses: list[AdSetAnalysis],
        overall_health: str,
    ) -> str:
        """Generate an LLM narrative for the campaign analysis."""
        system = (
            "You are a Meta Ads optimization analyst. Generate a concise "
            "performance summary (3-5 sentences) covering: overall health, "
            "key metrics vs targets, top/bottom performers, and actionable "
            "next steps."
        )
        user = (
            f"Campaign: {campaign.campaign_name}\n"
            f"Overall health: {overall_health}\n"
            f"Spend: ${insights.spend:.2f}, "
            f"CTR: {insights.ctr:.2f}%, "
            f"Frequency: {insights.frequency:.1f}\n"
            f"Ad sets:\n"
        )
        for a in analyses:
            user += (
                f"- {a.ad_set_name}: health={a.overall_health}, "
                f"CPA=${a.cpa_actual:.2f} ({a.cpa_status}), "
                f"ROAS={a.roas_actual:.2f}x ({a.roas_status})\n"
            )
        return await self._llm.generate(system, user)
