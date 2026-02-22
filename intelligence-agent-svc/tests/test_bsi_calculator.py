"""Tests for the Brand Strength Index (BSI) calculator."""

import pytest

from app.logic.iso_engine.bsi_calculator import BSICalculator
from app.logic.iso_engine.proxy_engine import ProxyEngine


class TestBSICalculator:
    """Validate BSI scoring with various pillar combinations."""

    def setup_method(self):
        self.calc = BSICalculator(proxy_engine=ProxyEngine())

    def test_all_pillars_present(self):
        """BSI with all three pillars should use standard weights."""
        result = self.calc.derive_index(
            financial_data={"score": 80},
            behavioral_data={"score": 70},
            legal_data={"score": 60},
        )
        # Weighted: 80*0.40 + 70*0.35 + 60*0.25 = 32 + 24.5 + 15 = 71.5
        assert result.score == 72  # rounded
        assert result.data_completeness == 1.0
        assert len(result.pillars) == 3

    def test_no_data_uses_stubs(self):
        """When no pillar data provided, use stub scores."""
        result = self.calc.derive_index()
        assert result.data_completeness == 0.0
        assert result.score > 0
        assert len(result.pillars) == 3

    def test_missing_financial_pillar(self):
        """Missing financial pillar triggers weight redistribution."""
        result = self.calc.derive_index(
            financial_data=None,
            behavioral_data={"score": 70},
            legal_data={"score": 60},
        )
        # Only behavioral + legal, redistributed weights
        # behavioral: 0.35/(0.35+0.25) = 0.583
        # legal: 0.25/(0.35+0.25) = 0.417
        assert result.data_completeness == pytest.approx(0.67, abs=0.01)
        assert len(result.pillars) == 2
        # Check weights sum to ~1.0
        total_weight = sum(p.weight for p in result.pillars)
        assert total_weight == pytest.approx(1.0, abs=0.01)

    def test_single_pillar_available(self):
        """Single pillar gets 100% of weight."""
        result = self.calc.derive_index(
            financial_data={"score": 85},
            behavioral_data=None,
            legal_data=None,
        )
        assert result.data_completeness == pytest.approx(0.33, abs=0.01)
        assert len(result.pillars) == 1
        assert result.pillars[0].weight == pytest.approx(1.0, abs=0.01)
        assert result.score == 85

    def test_financial_scoring_from_metrics(self):
        """Financial pillar scored from revenue growth and margin."""
        result = self.calc.derive_index(
            financial_data={
                "revenue_growth": 0.12,
                "profit_margin": 0.20,
            },
            behavioral_data={"score": 60},
            legal_data={"score": 50},
        )
        assert result.score > 0
        assert result.score <= 100

    def test_behavioral_scoring_from_metrics(self):
        """Behavioral pillar scored from awareness and sentiment."""
        result = self.calc.derive_index(
            financial_data={"score": 60},
            behavioral_data={
                "brand_awareness": 75,
                "sentiment_score": 80,
                "customer_loyalty": 70,
            },
            legal_data={"score": 50},
        )
        assert result.score > 0

    def test_legal_scoring_from_metrics(self):
        """Legal pillar scored from trademark and coverage."""
        result = self.calc.derive_index(
            financial_data={"score": 60},
            behavioral_data={"score": 60},
            legal_data={
                "trademark_strength": 85,
                "geographic_coverage": 70,
            },
        )
        assert result.score > 0

    def test_score_clamped_to_0_100(self):
        """BSI score should be clamped to [0, 100]."""
        result = self.calc.derive_index(
            financial_data={"score": 100},
            behavioral_data={"score": 100},
            legal_data={"score": 100},
        )
        assert result.score == 100

        result = self.calc.derive_index(
            financial_data={"score": 0},
            behavioral_data={"score": 0},
            legal_data={"score": 0},
        )
        assert result.score == 0

    def test_pillar_rationale_with_data(self):
        """Pillar rationale includes metric names."""
        result = self.calc.derive_index(
            financial_data={"revenue_growth": 0.10},
        )
        financial_pillar = next(p for p in result.pillars if p.name == "financial")
        assert "revenue_growth" in financial_pillar.rationale

    def test_pillar_rationale_without_data(self):
        """Missing data pillar rationale mentions stubs."""
        result = self.calc.derive_index()
        for pillar in result.pillars:
            assert "stub" in pillar.rationale.lower()
