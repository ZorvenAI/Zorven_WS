"""Tests for SKL-COA-05: Budget allocation analysis.

Tests reallocation from poor to good performers, net-zero validation,
and balance error correction.
"""

import pytest
from unittest.mock import MagicMock

from app.services.budget_analyzer import (
    BudgetAnalysis,
    BudgetAnalyzer,
    BudgetRecommendation,
)
from app.services.meta_insights_client import AdSetInsights, CampaignInsights


@pytest.fixture
def analyzer():
    return BudgetAnalyzer()


@pytest.fixture
def mock_campaign():
    camp = MagicMock()
    camp.campaign_id = "camp_001"
    return camp


def _make_ad_set(
    ad_set_id="adset_001",
    name="Test Ad Set",
    spend=100.0,
    cpa=20.0,
    roas=2.0,
):
    return AdSetInsights(
        ad_set_id=ad_set_id,
        ad_set_name=name,
        impressions=10000,
        clicks=300,
        spend=spend,
        ctr=3.0,
        cpm=10.0,
        frequency=1.5,
        reach=7000,
        conversions=max(1, int(spend / max(cpa, 0.01))),
        cost_per_action=cpa,
        purchase_roas=roas,
    )


# ── Underperformer Detection ────────────────────────────────────


class TestUnderperformerDetection:
    @pytest.mark.asyncio
    async def test_identifies_high_cpa_underperformer(
        self, analyzer, mock_campaign
    ):
        """Ad set with CPA > 2x target is marked as underperformer."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=300.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="bad",
                    spend=100.0,
                    cpa=110.0,  # > 2x of 50 target
                ),
                _make_ad_set(
                    ad_set_id="ok",
                    spend=200.0,
                    cpa=40.0,
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert "bad" in result.underperformers

    @pytest.mark.asyncio
    async def test_underperformer_budget_reduced(
        self, analyzer, mock_campaign
    ):
        """Underperformer's proposed budget is reduced by max_decrease_pct."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[
                _make_ad_set(ad_set_id="bad", spend=100.0, cpa=110.0),
                _make_ad_set(
                    ad_set_id="ok", spend=100.0, cpa=30.0, roas=2.0
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        bad_rec = next(
            r for r in result.recommendations if r.ad_set_id == "bad"
        )
        assert bad_rec.change_pct == -50
        assert bad_rec.proposed_budget < bad_rec.current_budget


# ── Winner Detection ─────────────────────────────────────────────


class TestWinnerDetection:
    @pytest.mark.asyncio
    async def test_identifies_high_roas_winner(
        self, analyzer, mock_campaign
    ):
        """Ad set with ROAS >= scale threshold is a winner."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="winner",
                    spend=200.0,
                    cpa=20.0,
                    roas=2.0,  # >= 1.5 threshold
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert "winner" in result.winners

    @pytest.mark.asyncio
    async def test_winner_budget_increased(
        self, analyzer, mock_campaign
    ):
        """Winner's proposed budget is increased by max_increase_pct."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="winner", spend=100.0, roas=2.0, cpa=20.0
                ),
                _make_ad_set(
                    ad_set_id="neutral", spend=100.0, roas=1.0, cpa=40.0
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        winner_rec = next(
            r for r in result.recommendations if r.ad_set_id == "winner"
        )
        assert winner_rec.change_pct == 20
        assert winner_rec.proposed_budget > winner_rec.current_budget


# ── Maintain Current ─────────────────────────────────────────────


class TestMaintainCurrent:
    @pytest.mark.asyncio
    async def test_average_performer_unchanged(
        self, analyzer, mock_campaign
    ):
        """Average performer keeps current budget."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=200.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="avg",
                    spend=200.0,
                    cpa=40.0,  # Below 2x, above 0.7x
                    roas=1.2,  # Below scale threshold
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        rec = result.recommendations[0]
        assert rec.change_pct == 0
        assert rec.proposed_budget == rec.current_budget


# ── Net-Zero / Balance Validation ────────────────────────────────


class TestBalanceValidation:
    @pytest.mark.asyncio
    async def test_balance_within_tolerance(
        self, analyzer, mock_campaign
    ):
        """When all ad sets maintain, balance error is 0."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=300.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="a1", spend=150.0, cpa=40.0, roas=1.2
                ),
                _make_ad_set(
                    ad_set_id="a2", spend=150.0, cpa=45.0, roas=1.2
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.balance_error_pct <= 5.0

    @pytest.mark.asyncio
    async def test_rebalance_on_large_imbalance(
        self, analyzer, mock_campaign
    ):
        """When imbalance > 5%, redistribute proportionally."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=500.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="bad",
                    spend=200.0,
                    cpa=110.0,
                ),
                _make_ad_set(
                    ad_set_id="winner",
                    spend=300.0,
                    cpa=20.0,
                    roas=2.0,
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        # After rebalancing, error should be <= 5%
        assert result.balance_error_pct <= 5.0

    @pytest.mark.asyncio
    async def test_zero_spend_no_error(self, analyzer, mock_campaign):
        """Zero total spend results in 0 balance error."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=0.0,
            ad_sets=[
                _make_ad_set(ad_set_id="a1", spend=0.0, cpa=0.0),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.balance_error_pct == 0.0


# ── Mixed Portfolio ──────────────────────────────────────────────


class TestMixedPortfolio:
    @pytest.mark.asyncio
    async def test_mixed_underperformer_and_winner(
        self, analyzer, mock_campaign
    ):
        """Portfolio with both underperformer and winner."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=500.0,
            ad_sets=[
                _make_ad_set(
                    ad_set_id="bad",
                    name="BOFU Retargeting",
                    spend=100.0,
                    cpa=110.0,
                ),
                _make_ad_set(
                    ad_set_id="good",
                    name="TOFU Tech",
                    spend=250.0,
                    cpa=20.0,
                    roas=2.0,
                ),
                _make_ad_set(
                    ad_set_id="avg",
                    name="MOFU Decision",
                    spend=150.0,
                    cpa=45.0,
                    roas=1.2,
                ),
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert "bad" in result.underperformers
        assert "good" in result.winners
        assert len(result.recommendations) == 3
        assert result.balance_error_pct <= 5.0

    @pytest.mark.asyncio
    async def test_total_budget_matches_spend(
        self, analyzer, mock_campaign
    ):
        """total_budget field should reflect input spend."""
        insights = CampaignInsights(
            campaign_id="camp_001",
            spend=750.0,
            ad_sets=[
                _make_ad_set(ad_set_id="a1", spend=750.0, cpa=40.0, roas=1.2)
            ],
        )
        result = await analyzer.analyze_budget(
            mock_campaign, insights, {"cpa_target": 50.0}
        )
        assert result.total_budget == 750.0
