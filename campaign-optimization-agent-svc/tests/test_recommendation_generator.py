"""Tests for SKL-COA-06: Recommendation generator.

Tests PAUSE/SCALE/REALLOCATE/REFRESH action types, priority
assignment, rationale generation, and projected impact.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.budget_analyzer import BudgetAnalysis, BudgetRecommendation
from app.services.fatigue_detector import FatigueReport, FatiguedAd
from app.services.performance_analyzer import AdSetAnalysis, CampaignAnalysis
from app.services.recommendation_generator import (
    REC_TTL_HOURS,
    RecommendationGenerator,
)


@pytest.fixture
def generator():
    return RecommendationGenerator(llm_client=None)


@pytest.fixture
def generator_with_llm():
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="LLM rationale text.")
    return RecommendationGenerator(llm_client=llm), llm


@pytest.fixture
def mock_campaign():
    camp = MagicMock()
    camp.campaign_id = "camp_001"
    camp.tenant_id = "tenant_001"
    camp.campaign_name = "Q2 Brand Awareness"
    return camp


@pytest.fixture
def green_analysis():
    return CampaignAnalysis(
        campaign_id="camp_001",
        overall_health="GREEN",
        ad_set_analyses=[
            AdSetAnalysis(
                ad_set_id="adset_001",
                cpa_status="OK",
                cpa_actual=40.0,
                cpa_target=50.0,
                overall_health="GREEN",
            ),
        ],
        green_count=1,
    )


@pytest.fixture
def empty_fatigue():
    return FatigueReport(campaign_id="camp_001")


@pytest.fixture
def empty_budget():
    return BudgetAnalysis(campaign_id="camp_001")


# ── PAUSE Recommendations ────────────────────────────────────────


class TestPauseRecommendations:
    @pytest.mark.asyncio
    async def test_pause_for_kill_cpa(
        self, generator, mock_campaign, empty_fatigue, empty_budget
    ):
        """KILL CPA status generates a PAUSE recommendation."""
        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            overall_health="RED",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_003",
                    cpa_status="KILL",
                    cpa_actual=110.0,
                    cpa_target=50.0,
                    overall_health="RED",
                    spend_pct=20.0,
                ),
            ],
            red_count=1,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, analysis, empty_fatigue, empty_budget, {}
        )
        pause_recs = [r for r in recs if r["action_type"] == "pause"]
        assert len(pause_recs) == 1
        assert pause_recs[0]["entity_type"] == "ad_set"
        assert pause_recs[0]["entity_id"] == "adset_003"
        assert pause_recs[0]["reason"] == "high_cpa"
        assert pause_recs[0]["priority"] == "high"

    @pytest.mark.asyncio
    async def test_pause_proposed_values(
        self, generator, mock_campaign, empty_fatigue, empty_budget
    ):
        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_003",
                    cpa_status="KILL",
                    cpa_actual=110.0,
                    cpa_target=50.0,
                    spend_pct=20.0,
                ),
            ],
            red_count=1,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, analysis, empty_fatigue, empty_budget, {}
        )
        assert recs[0]["proposed_values"] == {"status": "PAUSED"}


# ── SCALE Recommendations ────────────────────────────────────────


class TestScaleRecommendations:
    @pytest.mark.asyncio
    async def test_scale_for_good_cpa(
        self, generator, mock_campaign, empty_fatigue, empty_budget
    ):
        """SCALE CPA status generates a scale recommendation."""
        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_001",
                    cpa_status="SCALE",
                    cpa_actual=12.0,
                    cpa_target=50.0,
                    roas_actual=4.0,
                    overall_health="GREEN",
                ),
            ],
            green_count=1,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, analysis, empty_fatigue, empty_budget, {}
        )
        scale_recs = [r for r in recs if r["action_type"] == "scale"]
        assert len(scale_recs) == 1
        assert scale_recs[0]["priority"] == "medium"
        assert scale_recs[0]["reason"] == "strong_performance"


# ── CREATIVE REFRESH Recommendations ─────────────────────────────


class TestCreativeRefreshRecommendations:
    @pytest.mark.asyncio
    async def test_refresh_for_fatigued_ad(
        self, generator, mock_campaign, green_analysis, empty_budget
    ):
        """Fatigued ad with HIGH confidence generates refresh recommendation."""
        fatigue = FatigueReport(
            campaign_id="camp_001",
            fatigued_ads=[
                FatiguedAd(
                    ad_id="ad_002",
                    ad_name="Ad 2",
                    ad_set_id="adset_001",
                    ctr_current=1.5,
                    ctr_peak=4.0,
                    decline_pct=62.5,
                    frequency=3.0,
                    days_running=20,
                    confidence="HIGH",
                ),
            ],
            total_ads_analyzed=3,
            fatigue_rate=33.3,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, green_analysis, fatigue, empty_budget, {}
        )
        refresh = [r for r in recs if r["action_type"] == "creative_refresh"]
        assert len(refresh) == 1
        assert refresh[0]["priority"] == "high"

    @pytest.mark.asyncio
    async def test_no_refresh_for_low_confidence(
        self, generator, mock_campaign, green_analysis, empty_budget
    ):
        """LOW confidence fatigue does NOT generate a recommendation."""
        fatigue = FatigueReport(
            campaign_id="camp_001",
            fatigued_ads=[
                FatiguedAd(
                    ad_id="ad_002",
                    confidence="LOW",
                    decline_pct=25.0,
                ),
            ],
        )
        recs = await generator.generate_recommendations(
            mock_campaign, green_analysis, fatigue, empty_budget, {}
        )
        refresh = [r for r in recs if r["action_type"] == "creative_refresh"]
        assert len(refresh) == 0

    @pytest.mark.asyncio
    async def test_medium_confidence_gets_medium_priority(
        self, generator, mock_campaign, green_analysis, empty_budget
    ):
        fatigue = FatigueReport(
            campaign_id="camp_001",
            fatigued_ads=[
                FatiguedAd(
                    ad_id="ad_003",
                    confidence="MEDIUM",
                    decline_pct=30.0,
                ),
            ],
        )
        recs = await generator.generate_recommendations(
            mock_campaign, green_analysis, fatigue, empty_budget, {}
        )
        refresh = [r for r in recs if r["action_type"] == "creative_refresh"]
        assert len(refresh) == 1
        assert refresh[0]["priority"] == "medium"


# ── BUDGET ADJUSTMENT Recommendations ────────────────────────────


class TestBudgetAdjustmentRecommendations:
    @pytest.mark.asyncio
    async def test_adjust_budget_from_budget_analysis(
        self, generator, mock_campaign, green_analysis, empty_fatigue
    ):
        """Budget recommendations with change_pct != 0 generate adjust_budget."""
        budget = BudgetAnalysis(
            campaign_id="camp_001",
            recommendations=[
                BudgetRecommendation(
                    ad_set_id="adset_001",
                    current_budget=100.0,
                    proposed_budget=120.0,
                    change_pct=20,
                    reason="ROAS 2.0x exceeds scale threshold",
                    health="GREEN",
                ),
            ],
        )
        recs = await generator.generate_recommendations(
            mock_campaign, green_analysis, empty_fatigue, budget, {}
        )
        budget_recs = [r for r in recs if r["action_type"] == "adjust_budget"]
        assert len(budget_recs) == 1
        assert budget_recs[0]["proposed_values"]["daily_budget"] == 120.0

    @pytest.mark.asyncio
    async def test_no_rec_for_zero_change(
        self, generator, mock_campaign, green_analysis, empty_fatigue
    ):
        """Budget recommendation with 0% change is skipped."""
        budget = BudgetAnalysis(
            campaign_id="camp_001",
            recommendations=[
                BudgetRecommendation(
                    ad_set_id="adset_001",
                    current_budget=100.0,
                    proposed_budget=100.0,
                    change_pct=0,
                ),
            ],
        )
        recs = await generator.generate_recommendations(
            mock_campaign, green_analysis, empty_fatigue, budget, {}
        )
        budget_recs = [r for r in recs if r["action_type"] == "adjust_budget"]
        assert len(budget_recs) == 0

    @pytest.mark.asyncio
    async def test_high_priority_for_large_change(
        self, generator, mock_campaign, green_analysis, empty_fatigue
    ):
        """Change > 30% gets high priority."""
        budget = BudgetAnalysis(
            campaign_id="camp_001",
            recommendations=[
                BudgetRecommendation(
                    ad_set_id="adset_001",
                    current_budget=100.0,
                    proposed_budget=50.0,
                    change_pct=-50,
                    reason="CPA too high",
                ),
            ],
        )
        recs = await generator.generate_recommendations(
            mock_campaign, green_analysis, empty_fatigue, budget, {}
        )
        assert recs[0]["priority"] == "high"


# ── Recommendation Structure ─────────────────────────────────────


class TestRecommendationStructure:
    @pytest.mark.asyncio
    async def test_has_required_fields(
        self, generator, mock_campaign, empty_fatigue, empty_budget
    ):
        """Every recommendation has all required fields."""
        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_001",
                    cpa_status="KILL",
                    cpa_actual=110.0,
                    cpa_target=50.0,
                    spend_pct=20.0,
                ),
            ],
            red_count=1,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, analysis, empty_fatigue, empty_budget, {}
        )
        rec = recs[0]
        required = [
            "recommendation_id",
            "tenant_id",
            "campaign_id",
            "action_type",
            "entity_type",
            "entity_id",
            "current_values",
            "proposed_values",
            "reason",
            "rationale",
            "projected_impact",
            "priority",
            "status",
            "requires_approval",
            "created_at",
            "expires_at",
        ]
        for field in required:
            assert field in rec, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_status_is_pending(
        self, generator, mock_campaign, empty_fatigue, empty_budget
    ):
        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_001",
                    cpa_status="KILL",
                    spend_pct=0.0,
                ),
            ],
            red_count=1,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, analysis, empty_fatigue, empty_budget, {}
        )
        assert recs[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_no_recs_for_all_healthy(
        self, generator, mock_campaign, empty_fatigue, empty_budget
    ):
        """No recommendations when everything is healthy."""
        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_001",
                    cpa_status="OK",
                    overall_health="GREEN",
                ),
            ],
            green_count=1,
        )
        recs = await generator.generate_recommendations(
            mock_campaign, analysis, empty_fatigue, empty_budget, {}
        )
        assert len(recs) == 0


# ── LLM Rationale Enrichment ────────────────────────────────────


class TestRationaleEnrichment:
    @pytest.mark.asyncio
    async def test_llm_enriches_rationale(self, mock_campaign):
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="Enriched rationale text.")
        gen = RecommendationGenerator(llm_client=llm)

        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_001",
                    cpa_status="KILL",
                    spend_pct=0.0,
                ),
            ],
            red_count=1,
        )
        recs = await gen.generate_recommendations(
            mock_campaign,
            analysis,
            FatigueReport(campaign_id="camp_001"),
            BudgetAnalysis(campaign_id="camp_001"),
            {},
        )
        assert recs[0]["rationale"] == "Enriched rationale text."

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self, mock_campaign):
        """LLM failure doesn't break recommendations."""
        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=Exception("timeout"))
        gen = RecommendationGenerator(llm_client=llm)

        analysis = CampaignAnalysis(
            campaign_id="camp_001",
            ad_set_analyses=[
                AdSetAnalysis(
                    ad_set_id="adset_001",
                    cpa_status="KILL",
                    spend_pct=0.0,
                ),
            ],
            red_count=1,
        )
        recs = await gen.generate_recommendations(
            mock_campaign,
            analysis,
            FatigueReport(campaign_id="camp_001"),
            BudgetAnalysis(campaign_id="camp_001"),
            {},
        )
        # Should still have recommendations even if rationale enrichment failed
        assert len(recs) >= 1
