"""Main orchestration loop for Campaign Optimization Agent.

Executes the full optimization tick:
discover -> for each campaign: guardrails -> fetch insights ->
analyze -> detect fatigue -> analyze budget -> recommend ->
execute/queue -> verify -> persist -> callback
"""

import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.guardrails import InputGuardrails
from app.logic.state_machine import CampaignTickStateMachine, TickState
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.autonomous_executor import AutonomousExecutor
from app.services.budget_analyzer import BudgetAnalyzer
from app.services.callback_client import CallbackClient
from app.services.campaign_discovery import CampaignDiscovery
from app.services.fatigue_detector import FatigueDetector
from app.services.meta_insights_client import MetaInsightsClient
from app.services.meta_management_client import MetaManagementClient
from app.services.optimization_persister import OptimizationPersister
from app.services.optimization_verifier import OptimizationVerifier
from app.services.performance_analyzer import PerformanceAnalyzer
from app.services.recommendation_generator import RecommendationGenerator
from app.services.reporter import Reporter

logger = logging.getLogger(__name__)


class TickExecutor:
    """Orchestrates the full optimization tick."""

    def __init__(
        self,
        redis_manager: RedisManager | None = None,
        event_emitter: EventEmitter | None = None,
        llm_client=None,
    ):
        self._redis = redis_manager or RedisManager()
        self._emitter = event_emitter

        # Initialize service dependencies
        self._discovery = CampaignDiscovery(redis_manager=self._redis)
        self._insights_client = MetaInsightsClient(
            api_version=settings.META_API_VERSION,
            sandbox_mode=settings.META_ADS_SANDBOX_MODE,
        )
        self._meta_client = MetaManagementClient(
            api_version=settings.META_API_VERSION,
            sandbox_mode=settings.META_ADS_SANDBOX_MODE,
        )
        self._analyzer = PerformanceAnalyzer(llm_client=llm_client)
        self._fatigue_detector = FatigueDetector()
        self._budget_analyzer = BudgetAnalyzer()
        self._rec_generator = RecommendationGenerator(llm_client=llm_client)
        self._verifier = OptimizationVerifier()
        self._executor = AutonomousExecutor(
            meta_client=self._meta_client,
            verifier=self._verifier,
            event_emitter=self._emitter,
            redis_manager=self._redis,
        )
        self._callback = CallbackClient()
        self._persister = OptimizationPersister(
            callback_client=self._callback,
            redis_manager=self._redis,
        )
        self._reporter = Reporter(llm_client=llm_client)
        self._input_guardrails = InputGuardrails()

    async def execute_tick(
        self,
        campaign_age_min_days: int | None = None,
        campaign_age_max_days: int | None = None,
    ) -> dict[str, Any]:
        """Execute a full optimization tick.

        Args:
            campaign_age_min_days: Minimum campaign age filter.
            campaign_age_max_days: Maximum campaign age filter.

        Returns:
            Tick result summary dict.
        """
        tick_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        logger.info("Tick %s started", tick_id)

        if self._emitter:
            await self._emitter.emit(
                EventType.TICK_STARTED,
                data={
                    "tick_id": tick_id,
                    "age_min_days": campaign_age_min_days,
                    "age_max_days": campaign_age_max_days,
                },
            )

        # Connect Redis if needed
        if not self._redis.available:
            await self._redis.connect()

        # 1. Discover active campaigns
        campaigns = await self._discovery.discover_active_campaigns(
            age_min_days=campaign_age_min_days,
            age_max_days=campaign_age_max_days,
        )

        total_recs = 0
        total_actions = 0
        campaign_results = []

        # 2. Process each campaign
        for campaign in campaigns:
            result = await self._process_campaign(campaign, tick_id)
            campaign_results.append(result)
            total_recs += result.get("recommendations_generated", 0)
            total_actions += result.get("actions_executed", 0)

        elapsed_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        tick_result = {
            "tick_id": tick_id,
            "campaigns_processed": len(campaigns),
            "recommendations_generated": total_recs,
            "actions_executed": total_actions,
            "campaign_results": campaign_results,
            "elapsed_ms": elapsed_ms,
            "timestamp": start_time.isoformat(),
        }

        logger.info(
            "Tick %s completed: %d campaigns, %d recs, " "%d actions, %dms",
            tick_id,
            len(campaigns),
            total_recs,
            total_actions,
            elapsed_ms,
        )

        return tick_result

    @staticmethod
    def _build_performance(insights: Any) -> dict[str, Any]:
        """Build the `performance` payload consumed by Django's
        optimization tick callback to update CampaignRegistry.actual_*
        fields on the /optimization dashboard.

        Meta's Insights API returns CTR as a percent (e.g. 1.23 = 1.23%),
        which matches the analytics convention on the Django side.
        CPA is derived: spend / conversions (None when conversions=0).
        """
        spend = float(getattr(insights, "spend", 0) or 0)
        conv = int(getattr(insights, "conversions", 0) or 0)
        ctr = float(getattr(insights, "ctr", 0) or 0)
        roas = float(getattr(insights, "purchase_roas", 0) or 0)
        return {
            "avg_cpa": round(spend / conv, 2) if conv > 0 else None,
            "avg_roas": roas if roas > 0 else None,
            "avg_ctr": ctr if ctr > 0 else None,
            "spend_today": round(spend, 2),
        }

    async def _process_campaign(
        self,
        campaign: Any,
        tick_id: str,
    ) -> dict[str, Any]:
        """Process a single campaign through the optimization pipeline."""
        sm = CampaignTickStateMachine(campaign.campaign_id)
        sm.transition(TickState.DISCOVERING, "tick_start")

        # Load tenant config
        tenant_config = await self._discovery.load_tenant_config(campaign.tenant_id)

        # Input guardrails
        campaign_dict = {
            "campaign_id": campaign.campaign_id,
            "meta_access_token": campaign.meta_access_token,
            "meta_ad_account_id": campaign.meta_ad_account_id,
            "total_spend_usd": campaign.total_spend_usd,
            "total_impressions": campaign.total_impressions,
            "created_at": campaign.created_at,
            "last_optimized_at": campaign.last_optimized_at,
            "daily_action_count": campaign.daily_action_count,
            "sandbox_mode": campaign.sandbox_mode,
            "optimization_count": campaign.optimization_count,
            "active_ad_set_count": campaign.active_ad_set_count,
        }
        guard_report = self._input_guardrails.check(
            campaign=campaign_dict,
            tenant_config=tenant_config,
            settings=settings,
        )

        if guard_report.blocked or not guard_report.all_passed:
            skip_reasons = [f.message for f in guard_report.failures]
            # Hard-skip rules mean we cannot fetch insights (no creds /
            # invalid campaign / sandbox off with no config). All other
            # failures (minimum-data, age, cooldown, daily cap) are
            # "soft" skips — the campaign is valid, it just shouldn't be
            # optimized this tick. For soft skips we still fetch
            # insights and post a metrics-only callback so the
            # /optimization dashboard stays populated.
            # In sandbox mode the insights client returns stub data
            # without calling Meta, so IG-02 (missing Meta credentials)
            # is not a real blocker — demote it to a soft skip so the
            # dashboard still gets stubbed KPIs.
            hard_skip_rules = {"IG-01", "IG-07", "IG-08"}
            if not settings.META_ADS_SANDBOX_MODE:
                hard_skip_rules.add("IG-02")
            is_hard_skip = any(
                f.rule_id in hard_skip_rules for f in guard_report.failures
            )
            if not is_hard_skip:
                try:
                    insights = await self._insights_client.fetch_campaign_insights(
                        ad_account_id=campaign.meta_ad_account_id,
                        campaign_id=(campaign.meta_campaign_id or campaign.campaign_id),
                        access_token=campaign.meta_access_token,
                    )
                    metrics_only_results = {
                        "tick_id": tick_id,
                        "campaign_id": campaign.campaign_id,
                        "performance": self._build_performance(insights),
                        "metrics": {
                            "spend": insights.spend,
                            "ctr": insights.ctr,
                            "cpm": insights.cpm,
                            "frequency": insights.frequency,
                            "conversions": insights.conversions,
                            "roas": insights.purchase_roas,
                        },
                        "recommendations_generated": 0,
                        "actions_executed": 0,
                        "skip_reasons": skip_reasons,
                    }
                    await self._persister.persist_tick_results(
                        tenant_id=campaign.tenant_id,
                        campaign_id=campaign.campaign_id,
                        tick_results=metrics_only_results,
                    )
                except Exception as exc:
                    logger.warning(
                        "Metrics-only callback failed for %s: %s",
                        campaign.campaign_id,
                        exc,
                    )
            sm.transition(TickState.SKIPPED, "; ".join(skip_reasons))
            return {
                "campaign_id": campaign.campaign_id,
                "status": "skipped",
                "reasons": skip_reasons,
                "recommendations_generated": 0,
                "actions_executed": 0,
            }

        # Fetch insights
        sm.transition(TickState.FETCHING_INSIGHTS, "guardrails_passed")
        try:
            insights = await self._insights_client.fetch_campaign_insights(
                ad_account_id=campaign.meta_ad_account_id,
                campaign_id=campaign.meta_campaign_id or campaign.campaign_id,
                access_token=campaign.meta_access_token,
            )
        except Exception as exc:
            logger.error(
                "Failed to fetch insights for %s: %s",
                campaign.campaign_id,
                exc,
            )
            sm.transition(TickState.SKIPPED, f"insights_error: {exc}")
            return {
                "campaign_id": campaign.campaign_id,
                "status": "skipped",
                "reasons": [f"Insights fetch failed: {exc}"],
                "recommendations_generated": 0,
                "actions_executed": 0,
            }

        # Analyze
        sm.transition(TickState.ANALYZING, "insights_fetched")
        analysis = await self._analyzer.analyze_campaign(
            campaign=campaign,
            insights=insights,
            config=tenant_config,
        )

        if self._emitter:
            await self._emitter.emit(
                EventType.CAMPAIGN_ANALYZED,
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.campaign_id,
                data={"health": analysis.overall_health},
            )

        # Detect fatigue
        ctr_peaks = {}
        if self._redis:
            ctr_peaks = await self._redis.get_ctr_peaks(
                campaign.tenant_id, campaign.campaign_id
            )
        fatigue_report = await self._fatigue_detector.detect_fatigue(
            campaign_id=campaign.campaign_id,
            ad_insights=insights.ads,
            ctr_peaks=ctr_peaks,
            config=tenant_config,
        )

        if fatigue_report.fatigued_ads and self._emitter:
            await self._emitter.emit(
                EventType.FATIGUE_DETECTED,
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.campaign_id,
                data={"fatigued_count": len(fatigue_report.fatigued_ads)},
            )

        # Analyze budget
        budget_analysis = await self._budget_analyzer.analyze_budget(
            campaign=campaign,
            insights=insights,
            config=tenant_config,
        )

        # Check if any action needed
        has_issues = (
            analysis.red_count > 0
            or analysis.yellow_count > 0
            or fatigue_report.fatigued_ads
            or budget_analysis.underperformers
            or budget_analysis.winners
        )

        if not has_issues:
            sm.transition(TickState.NO_ACTION, "all_healthy")
            sm.transition(TickState.COMPLETED, "no_action_needed")
            return {
                "campaign_id": campaign.campaign_id,
                "status": "no_action",
                "health": analysis.overall_health,
                "recommendations_generated": 0,
                "actions_executed": 0,
            }

        # Generate recommendations
        sm.transition(TickState.RECOMMENDING, "issues_found")
        recommendations = await self._rec_generator.generate_recommendations(
            campaign=campaign,
            analysis=analysis,
            fatigue_report=fatigue_report,
            budget_analysis=budget_analysis,
            config=tenant_config,
        )

        if self._emitter:
            for rec in recommendations:
                await self._emitter.emit(
                    EventType.RECOMMENDATION_CREATED,
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.campaign_id,
                    data={
                        "recommendation_id": rec["recommendation_id"],
                        "action_type": rec["action_type"],
                    },
                )

        # Store recommendations in Redis
        if self._redis:
            for rec in recommendations:
                await self._redis.store_recommendation(
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.campaign_id,
                    recommendation=rec,
                )

        # Execute autonomous actions
        sm.transition(TickState.EXECUTING, "recommendations_ready")
        self._verifier.reset_spend_tracking()
        execution_results = await self._executor.execute_autonomous(
            campaign=campaign,
            recommendations=recommendations,
            config=tenant_config,
        )

        actions_executed = sum(1 for r in execution_results if r.get("executed", False))

        # Persist results
        sm.transition(TickState.PERSISTING, "execution_complete")
        tick_results = {
            "tick_id": tick_id,
            "campaign_id": campaign.campaign_id,
            "overall_health": analysis.overall_health,
            "performance": self._build_performance(insights),
            "metrics": {
                "spend": insights.spend,
                "ctr": insights.ctr,
                "cpm": insights.cpm,
                "frequency": insights.frequency,
                "conversions": insights.conversions,
                "roas": insights.purchase_roas,
            },
            "recommendations": recommendations,
            "execution_results": execution_results,
            "recommendations_generated": len(recommendations),
            "actions_executed": actions_executed,
            "fatigue_detected": len(fatigue_report.fatigued_ads),
        }

        await self._persister.persist_tick_results(
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.campaign_id,
            tick_results=tick_results,
        )

        # Update CTR peaks
        if self._redis:
            for ad in insights.ads:
                await self._redis.set_ctr_peak(
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.campaign_id,
                    ad_id=ad.ad_id,
                    ctr=ad.ctr,
                )

        sm.transition(TickState.COMPLETED, "tick_done")

        return {
            "campaign_id": campaign.campaign_id,
            "status": "completed",
            "health": analysis.overall_health,
            "recommendations_generated": len(recommendations),
            "actions_executed": actions_executed,
            "state_history": sm.history,
        }
