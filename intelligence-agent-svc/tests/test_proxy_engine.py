"""Tests for the ProxyEngine weight redistribution."""

import pytest

from app.logic.iso_engine.proxy_engine import ProxyEngine


class TestProxyEngine:
    """Validate weight redistribution and data completeness assessment."""

    def setup_method(self):
        self.engine = ProxyEngine()

    def test_full_data_standard_mode(self):
        """Full data → STANDARD_ROYALTY_RELIEF strategy."""
        strategy = self.engine.get_calculation_strategy(
            {"financial_data": {"revenue": 1_000_000}}
        )
        assert strategy == "STANDARD_ROYALTY_RELIEF"

    def test_missing_financial_price_premium_mode(self):
        """No financial data → PRICE_PREMIUM_MODE."""
        strategy = self.engine.get_calculation_strategy(
            {"financial_data": None}
        )
        assert strategy == "PRICE_PREMIUM_MODE"

    def test_empty_financial_price_premium_mode(self):
        """Empty financial data dict → PRICE_PREMIUM_MODE."""
        strategy = self.engine.get_calculation_strategy(
            {"financial_data": {}}
        )
        assert strategy == "PRICE_PREMIUM_MODE"

    def test_redistribute_all_pillars(self):
        """All pillars present → weights unchanged."""
        default_weights = {
            "financial": 0.40,
            "behavioral": 0.35,
            "legal": 0.25,
        }
        result = self.engine.redistribute_weights(
            ["financial", "behavioral", "legal"],
            default_weights,
        )
        assert result["financial"] == pytest.approx(0.40, abs=0.001)
        assert result["behavioral"] == pytest.approx(0.35, abs=0.001)
        assert result["legal"] == pytest.approx(0.25, abs=0.001)

    def test_redistribute_missing_financial(self):
        """DDD spec example: financial missing → behavioral 58.3%, legal 41.7%."""
        default_weights = {
            "financial": 0.40,
            "behavioral": 0.35,
            "legal": 0.25,
        }
        result = self.engine.redistribute_weights(
            ["behavioral", "legal"],
            default_weights,
        )
        assert result["behavioral"] == pytest.approx(0.583, abs=0.001)
        assert result["legal"] == pytest.approx(0.417, abs=0.001)
        assert sum(result.values()) == pytest.approx(1.0, abs=0.001)

    def test_redistribute_single_pillar(self):
        """Single pillar gets 100% weight."""
        default_weights = {
            "financial": 0.40,
            "behavioral": 0.35,
            "legal": 0.25,
        }
        result = self.engine.redistribute_weights(
            ["behavioral"],
            default_weights,
        )
        assert result["behavioral"] == pytest.approx(1.0, abs=0.001)

    def test_redistribute_empty_pillars(self):
        """No available pillars → empty dict."""
        result = self.engine.redistribute_weights(
            [],
            {"financial": 0.40, "behavioral": 0.35, "legal": 0.25},
        )
        assert result == {}

    def test_data_completeness_all_present(self):
        """All three pillars → 1.0 completeness."""
        completeness = self.engine.assess_data_completeness(
            financial_data={"rev": 100},
            behavioral_data={"awareness": 80},
            legal_data={"trademark": 90},
        )
        assert completeness == pytest.approx(1.0)

    def test_data_completeness_none_present(self):
        """No pillars → 0.0 completeness."""
        completeness = self.engine.assess_data_completeness(
            financial_data=None,
            behavioral_data=None,
            legal_data=None,
        )
        assert completeness == pytest.approx(0.0)

    def test_data_completeness_one_present(self):
        """One pillar → 1/3 completeness."""
        completeness = self.engine.assess_data_completeness(
            financial_data={"rev": 100},
            behavioral_data=None,
            legal_data=None,
        )
        assert completeness == pytest.approx(1.0 / 3.0)

    def test_data_completeness_two_present(self):
        """Two pillars → 2/3 completeness."""
        completeness = self.engine.assess_data_completeness(
            financial_data={"rev": 100},
            behavioral_data=None,
            legal_data={"trademark": 90},
        )
        assert completeness == pytest.approx(2.0 / 3.0)
