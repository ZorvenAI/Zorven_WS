"""Tests for SKL-COA-03: Performance analysis engine.

Tests CPA kill/scale/OK classification, ROAS thresholds,
frequency status, spend pacing, and overall campaign health.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.meta_insights_client import (
    AdSetInsights,
    CampaignInsights,
)
from app.services.performance_analyzer import (
    AdSetAnalysis,
    CampaignAnalysis,
    PerformanceAnalyzer,
)


@pytest.fixture
def analyzer():
    """PerformanceAnalyzer without LLM client."""
    return PerformanceAnalyzer(llm_client=None)


@pytest.fixture
def analyzer_with_llm():
    """PerformanceAnalyzer with mock LLM."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Analysis narrative text.")
    return PerformanceAnalyzer(llm_client=llm), llm


@pytest.fixture
def mock_campaign():
    camp = MagicMock()
    camp.campaign_id = "camp_001"
    camp.campaign_name = "Q2 Brand Awareness"
    return camp


def _make_ad_set(
    ad_set_id="adset_001",
    name="Test Ad Set",
    cpa=15.0,
    roas=2.0,
    frequency=1.5,
    spend=100.0,
):
    return AdSetInsights(
        ad_set_id=ad_set_id,
        ad_set_name=name,
        impressions=10000,
        clicks=300,
        spend=spend,
        ctr=3.0,
        cpm=10.0,
        frequency=frequency,
        reach=7000,
        conversions=max(1, int(spend / max(cpa, 0.01))),
        cost_per_action=cpa,
        purchase_roas=roas,
    )


# ── CPA Classification ──────────────────────────────────────────


class TestCPAClassification:
    @pytest.mark.asyncio
    async def test_cpa_kill_when_above_2x_target(self, analyzer, mock_campaign):
        """CPA > 2x target -> KILL status."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=110.0)],  # 2.2x of 50.0 target
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].cpa_status == "KILL"

    @pytest.mark.asyncio
    async def test_cpa_scale_when_below_70pct(self, analyzer, mock_campaign):
        """CPA < 70% of target -> SCALE status."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=30.0)],  # 60% of 50.0 target
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].cpa_status == "SCALE"

    @pytest.mark.asyncio
    async def test_cpa_ok_within_range(self, analyzer, mock_campaign):
        """CPA between 70% and 2x target -> OK."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=45.0)],  # 90% of 50.0 target
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].cpa_status == "OK"


# ── ROAS Classification ─────────────────────────────────────────


class TestROASClassification:
    @pytest.mark.asyncio
    async def test_roas_kill_below_half_target(self, analyzer, mock_campaign):
        """ROAS < 0.5x target -> KILL."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(roas=0.3, cpa=45.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0, "roas_target": 2.0}
        )
        assert result.ad_set_analyses[0].roas_status == "KILL"

    @pytest.mark.asyncio
    async def test_roas_scale_above_threshold(self, analyzer, mock_campaign):
        """ROAS >= scale_threshold (1.5) -> SCALE."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(roas=2.0, cpa=45.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0, "roas_target": 2.0}
        )
        assert result.ad_set_analyses[0].roas_status == "SCALE"

    @pytest.mark.asyncio
    async def test_roas_ok_between(self, analyzer, mock_campaign):
        """ROAS between 0.5x target and scale threshold -> OK."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(roas=1.2, cpa=45.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0, "roas_target": 2.0}
        )
        assert result.ad_set_analyses[0].roas_status == "OK"


# ── Frequency Analysis ───────────────────────────────────────────


class TestFrequencyAnalysis:
    @pytest.mark.asyncio
    async def test_high_frequency(self, analyzer, mock_campaign):
        """Frequency > 3.0 -> HIGH status."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(frequency=3.5, cpa=45.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].frequency_status == "HIGH"

    @pytest.mark.asyncio
    async def test_ok_frequency(self, analyzer, mock_campaign):
        """Frequency <= 3.0 -> OK status."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(frequency=2.0, cpa=45.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].frequency_status == "OK"


# ── Overall Health ───────────────────────────────────────────────


class TestOverallHealth:
    @pytest.mark.asyncio
    async def test_red_health(self, analyzer, mock_campaign):
        """Ad set with KILL CPA -> RED health."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=110.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].overall_health == "RED"

    @pytest.mark.asyncio
    async def test_yellow_health_high_frequency(self, analyzer, mock_campaign):
        """High frequency with OK CPA -> YELLOW."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(frequency=3.5, cpa=45.0, roas=1.2)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].overall_health == "YELLOW"

    @pytest.mark.asyncio
    async def test_green_health(self, analyzer, mock_campaign):
        """All metrics OK -> GREEN."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=45.0, roas=1.2, frequency=2.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.ad_set_analyses[0].overall_health == "GREEN"

    @pytest.mark.asyncio
    async def test_campaign_red_when_majority_red(self, analyzer, mock_campaign):
        """Campaign overall RED when > 50% ad sets are RED."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=400.0,
            ad_sets=[
                _make_ad_set(ad_set_id="a1", cpa=110.0, spend=100.0),
                _make_ad_set(ad_set_id="a2", cpa=110.0, spend=100.0),
                _make_ad_set(ad_set_id="a3", cpa=45.0, spend=200.0),
            ],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.overall_health == "RED"
        assert result.red_count == 2

    @pytest.mark.asyncio
    async def test_campaign_green_all_healthy(self, analyzer, mock_campaign):
        """Campaign overall GREEN when all ad sets healthy."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[
                _make_ad_set(ad_set_id="a1", cpa=40.0, roas=1.2, spend=100.0),
                _make_ad_set(ad_set_id="a2", cpa=35.0, roas=1.3, spend=100.0),
            ],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.overall_health == "GREEN"


# ── Narrative Generation ─────────────────────────────────────────


class TestNarrativeGeneration:
    @pytest.mark.asyncio
    async def test_narrative_with_llm(self, mock_campaign):
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="The campaign is performing well.")
        analyzer = PerformanceAnalyzer(llm_client=llm)

        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ctr=3.0,
            frequency=2.0,
            ad_sets=[_make_ad_set(cpa=40.0, roas=1.2)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.narrative == "The campaign is performing well."
        llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_narrative_degrades_gracefully(self, mock_campaign):
        """LLM failure should not break analysis."""
        llm = AsyncMock()
        llm.generate = AsyncMock(side_effect=Exception("LLM timeout"))
        analyzer = PerformanceAnalyzer(llm_client=llm)

        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=40.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.narrative == ""
        assert result.overall_health in ("GREEN", "YELLOW", "RED")

    @pytest.mark.asyncio
    async def test_no_narrative_without_llm(self, analyzer, mock_campaign):
        """No LLM client -> empty narrative."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[_make_ad_set(cpa=40.0)],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.narrative == ""


# ── Spend Pacing ─────────────────────────────────────────────────


class TestSpendPacing:
    @pytest.mark.asyncio
    async def test_overspending(self, analyzer, mock_campaign):
        """Ad set consuming > 60% of total -> OVERSPENDING."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=100.0,
            ad_sets=[
                _make_ad_set(ad_set_id="a1", spend=70.0, cpa=45.0),
                _make_ad_set(ad_set_id="a2", spend=30.0, cpa=45.0),
            ],
        )
        result = await analyzer.analyze_campaign(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        a1 = result.ad_set_analyses[0]
        assert a1.pacing_status == "OVERSPENDING"
        assert a1.spend_pct == 70.0
