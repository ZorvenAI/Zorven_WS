"""SKL-COA-06: Recommendation generator.

Generates OptimizationRecommendation records with action type,
current/proposed values, rationale, projected impact, and priority.
Uses Claude for human-readable rationale narratives.
"""

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.prompts.fallbacks import FALLBACK_RECOMMENDATION
from app.services.anthropic_client import AnthropicClient
from app.services.budget_analyzer import BudgetAnalysis
from app.services.fatigue_detector import FatigueReport
from app.services.performance_analyzer import CampaignAnalysis

logger = logging.getLogger(__name__)

# Recommendation TTL: 48 hours
REC_TTL_HOURS = 48


class RecommendationGenerator:
    """Generates optimization recommendations from analysis results."""

    def __init__(
        self,
        llm_client: AnthropicClient | None = None,
        prompt_loader: Any = None,
    ):
        self._llm = llm_client
        self._prompt_loader = prompt_loader

    async def generate_recommendations(
        self,
        campaign: Any,
        analysis: CampaignAnalysis,
        fatigue_report: FatigueReport,
        budget_analysis: BudgetAnalysis,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate optimization recommendations.

        Args:
            campaign: ActiveCampaign dataclass.
            analysis: CampaignAnalysis results.
            fatigue_report: FatigueReport results.
            budget_analysis: BudgetAnalysis results.
            config: Tenant optimization config.

        Returns:
            List of recommendation dicts ready for storage/approval.
        """
        recommendations = []
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=REC_TTL_HOURS)

        # Generate from ad set analyses
        for ad_set in analysis.ad_set_analyses:
            if ad_set.cpa_status == "KILL":
                rec = self._build_recommendation(
                    campaign=campaign,
                    action_type="pause",
                    entity_type="ad_set",
                    entity_id=ad_set.ad_set_id,
                    current_values={
                        "status": "ACTIVE",
                        "cpa": ad_set.cpa_actual,
                        "daily_budget": ad_set.spend_pct,
                    },
                    proposed_values={"status": "PAUSED"},
                    reason="high_cpa",
                    priority="high",
                    now=now,
                    expires=expires,
                )
                recommendations.append(rec)

            elif ad_set.cpa_status == "SCALE":
                rec = self._build_recommendation(
                    campaign=campaign,
                    action_type="scale",
                    entity_type="ad_set",
                    entity_id=ad_set.ad_set_id,
                    current_values={
                        "cpa": ad_set.cpa_actual,
                        "roas": ad_set.roas_actual,
                    },
                    proposed_values={"budget_increase_pct": 20},
                    reason="strong_performance",
                    priority="medium",
                    now=now,
                    expires=expires,
                )
                recommendations.append(rec)

        # Generate from fatigue detection
        for ad in fatigue_report.fatigued_ads:
            if ad.confidence in ("HIGH", "MEDIUM"):
                rec = self._build_recommendation(
                    campaign=campaign,
                    action_type="creative_refresh",
                    entity_type="ad",
                    entity_id=ad.ad_id,
                    current_values={
                        "ctr": ad.ctr_current,
                        "ctr_peak": ad.ctr_peak,
                        "decline_pct": ad.decline_pct,
                        "frequency": ad.frequency,
                    },
                    proposed_values={"action": "request_creative_refresh"},
                    reason="creative_fatigue",
                    priority=("high" if ad.confidence == "HIGH" else "medium"),
                    now=now,
                    expires=expires,
                )
                recommendations.append(rec)

        # Generate from budget analysis
        for budget_rec in budget_analysis.recommendations:
            if budget_rec.change_pct != 0:
                rec = self._build_recommendation(
                    campaign=campaign,
                    action_type="adjust_budget",
                    entity_type="ad_set",
                    entity_id=budget_rec.ad_set_id,
                    current_values={
                        "daily_budget": budget_rec.current_budget,
                    },
                    proposed_values={
                        "daily_budget": budget_rec.proposed_budget,
                    },
                    reason=budget_rec.reason,
                    priority=("high" if abs(budget_rec.change_pct) > 30 else "medium"),
                    now=now,
                    expires=expires,
                )
                recommendations.append(rec)

        # Generate LLM rationales (batch)
        if self._llm and recommendations:
            try:
                await self._enrich_rationales(recommendations, campaign)
            except Exception as exc:
                logger.error(
                    "Rationale enrichment failed (%s): %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                )

        logger.info(
            "Generated %d recommendations for campaign %s",
            len(recommendations),
            campaign.campaign_id,
        )
        return recommendations

    def _build_recommendation(
        self,
        campaign: Any,
        action_type: str,
        entity_type: str,
        entity_id: str,
        current_values: dict[str, Any],
        proposed_values: dict[str, Any],
        reason: str,
        priority: str,
        now: datetime,
        expires: datetime,
    ) -> dict[str, Any]:
        """Build a single recommendation dict."""
        return {
            "recommendation_id": str(uuid.uuid4()),
            "tenant_id": campaign.tenant_id,
            "campaign_id": campaign.campaign_id,
            "action_type": action_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "current_values": current_values,
            "proposed_values": proposed_values,
            "reason": reason,
            "rationale": "",  # Enriched by LLM later
            "projected_impact": {},
            "priority": priority,
            "status": "pending",
            "requires_approval": True,  # Determined by guardrails later
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }

    async def _enrich_rationales(
        self,
        recommendations: list[dict[str, Any]],
        campaign: Any,
    ):
        """Use Claude to generate human-readable rationales."""
        if self._prompt_loader is not None:
            system = await self._prompt_loader.load(
                "zorven-wf3-coa-recommendation",
                fallback=FALLBACK_RECOMMENDATION,
            )
        else:
            system = FALLBACK_RECOMMENDATION
        for rec in recommendations:
            user = (
                f"Campaign: {campaign.campaign_name}\n"
                f"Action: {rec['action_type']} on {rec['entity_type']} "
                f"{rec['entity_id']}\n"
                f"Reason: {rec['reason']}\n"
                f"Current: {rec['current_values']}\n"
                f"Proposed: {rec['proposed_values']}\n"
            )
            try:
                rationale = await self._llm.generate(
                    system, user, max_tokens=256, temperature=0.3
                )
                rec["rationale"] = rationale
            except Exception:
                rec["rationale"] = rec["reason"]
