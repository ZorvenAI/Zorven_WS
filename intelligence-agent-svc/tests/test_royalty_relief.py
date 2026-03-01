"""Tests for the Royalty Relief NPV calculation engine."""

from app.logic.iso_engine.royalty_relief import RoyaltyReliefEngine


class TestRoyaltyReliefEngine:
    """Validate Royalty Relief NPV math against hand-calculated values."""

    def setup_method(self):
        self.engine = RoyaltyReliefEngine()

    def test_npv_with_known_values(self):
        """Verify NPV against hand-calculated expected value.

        Explicit period (flat $1M revenue):
        Year 1-5: 1,000,000 * 0.05 * 0.75 / 1.10^t → sum ≈ 142,154.52

        Terminal value (Gordon Growth, g=2.5%):
        TV = (37,500 * 1.025) / (0.10 - 0.025) = 512,500.00
        PV(TV) = 512,500 / 1.10^5 ≈ 318,222.16

        Total NPV ≈ 142,154.52 + 318,222.16 = 460,376.68
        """
        result = self.engine.calculate_npv(
            projected_revenues=[1_000_000] * 5,
            royalty_rate=0.05,
            discount_rate=0.10,
            tax_rate=0.25,
        )
        assert abs(result.brand_value_npv - 460376.68) < 1.0
        assert result.royalty_rate == 0.05
        assert result.discount_rate == 0.10
        assert result.tax_rate == 0.25
        assert result.horizon_years == 5
        assert len(result.annual_royalties) == 5
        assert result.methodology == "royalty_relief"

    def test_zero_revenues_returns_zero_npv(self):
        """Zero revenues should produce zero NPV."""
        result = self.engine.calculate_npv(
            projected_revenues=[0, 0, 0],
            royalty_rate=0.05,
            discount_rate=0.10,
        )
        assert result.brand_value_npv == 0.0
        assert result.horizon_years == 3

    def test_empty_revenues_returns_zero(self):
        """Empty revenue list returns zero NPV."""
        result = self.engine.calculate_npv(
            projected_revenues=[],
            royalty_rate=0.05,
            discount_rate=0.10,
        )
        assert result.brand_value_npv == 0.0
        assert result.horizon_years == 0
        assert result.annual_royalties == []

    def test_single_year_horizon(self):
        """Single year explicit + terminal value.

        Explicit: 500,000 * 0.04 * 0.75 / 1.08 = 13,888.89
        TV = (15,000 * 1.025) / (0.08 - 0.025) = 279,545.45
        PV(TV) = 279,545.45 / 1.08 = 258,838.38
        Total ≈ 272,727.27
        """
        result = self.engine.calculate_npv(
            projected_revenues=[500_000],
            royalty_rate=0.04,
            discount_rate=0.08,
            tax_rate=0.25,
        )
        explicit = 500_000 * 0.04 * 0.75 / 1.08
        tv = (15_000 * 1.025) / (0.08 - 0.025)
        pv_tv = tv / 1.08
        expected = explicit + pv_tv
        assert abs(result.brand_value_npv - expected) < 0.01
        assert result.horizon_years == 1

    def test_increasing_revenues(self):
        """Increasing revenues should produce higher NPV than flat."""
        flat_result = self.engine.calculate_npv(
            projected_revenues=[1_000_000] * 5,
            royalty_rate=0.04,
            discount_rate=0.10,
        )
        increasing = [1_000_000 * (1.05**t) for t in range(5)]
        increasing_result = self.engine.calculate_npv(
            projected_revenues=increasing,
            royalty_rate=0.04,
            discount_rate=0.10,
        )
        assert increasing_result.brand_value_npv > flat_result.brand_value_npv

    def test_annual_royalties_are_post_tax(self):
        """Annual royalties should be Revenue * RoyaltyRate * (1 - TaxRate)."""
        result = self.engine.calculate_npv(
            projected_revenues=[1_000_000],
            royalty_rate=0.05,
            discount_rate=0.10,
            tax_rate=0.30,
        )
        expected_royalty = 1_000_000 * 0.05 * (1 - 0.30)
        assert abs(result.annual_royalties[0] - expected_royalty) < 0.01

    def test_higher_discount_rate_lowers_npv(self):
        """Higher discount rate should produce lower NPV."""
        low_discount = self.engine.calculate_npv(
            projected_revenues=[1_000_000] * 5,
            royalty_rate=0.04,
            discount_rate=0.08,
        )
        high_discount = self.engine.calculate_npv(
            projected_revenues=[1_000_000] * 5,
            royalty_rate=0.04,
            discount_rate=0.15,
        )
        assert low_discount.brand_value_npv > high_discount.brand_value_npv


class TestRevenueEstimation:
    """Test revenue estimation from context."""

    def setup_method(self):
        self.engine = RoyaltyReliefEngine()

    def test_user_provided_forecast(self):
        """Direct revenue forecast from input_context takes priority."""
        revenues = self.engine.estimate_revenues_from_context(
            previous_outputs={},
            input_context={"projected_revenues": [100, 200, 300]},
        )
        assert revenues == [100.0, 200.0, 300.0]

    def test_base_revenue_with_growth(self):
        """Base revenue + growth rate extrapolation."""
        revenues = self.engine.estimate_revenues_from_context(
            previous_outputs={},
            input_context={"base_revenue": 1_000_000, "growth_rate": 0.10},
            horizon_years=3,
        )
        assert len(revenues) == 3
        assert revenues[0] == 1_000_000.0
        assert abs(revenues[1] - 1_100_000.0) < 1.0
        assert abs(revenues[2] - 1_210_000.0) < 1.0

    def test_discovery_extraction(self):
        """Revenue extracted from previous node outputs."""
        revenues = self.engine.estimate_revenues_from_context(
            previous_outputs={"financial_research": {"estimated_revenue": 2_000_000}},
            input_context={},
            horizon_years=3,
        )
        assert len(revenues) == 3
        assert revenues[0] == 2_000_000.0

    def test_no_data_returns_empty(self):
        """When no data available, return empty list (error signal)."""
        revenues = self.engine.estimate_revenues_from_context(
            previous_outputs={},
            input_context={},
            horizon_years=5,
        )
        assert revenues == []


class TestRoyaltyRateSelection:
    """Test sector-based royalty rate selection."""

    def test_known_sector(self):
        assert RoyaltyReliefEngine.select_royalty_rate("technology") == 0.04
        assert RoyaltyReliefEngine.select_royalty_rate("healthcare") == 0.045
        assert RoyaltyReliefEngine.select_royalty_rate("luxury") == 0.05

    def test_unknown_sector_returns_default(self):
        assert RoyaltyReliefEngine.select_royalty_rate("unknown_sector") == 0.04

    def test_benchmark_override(self):
        benchmarks = {"technology": 0.06}
        assert RoyaltyReliefEngine.select_royalty_rate("technology", benchmarks) == 0.06

    def test_case_insensitive(self):
        assert RoyaltyReliefEngine.select_royalty_rate("Technology") == 0.04
        assert RoyaltyReliefEngine.select_royalty_rate("HEALTHCARE") == 0.045


class TestBuildRationale:
    """Test rationale text generation."""

    def test_rationale_includes_key_fields(self):
        engine = RoyaltyReliefEngine()
        result = engine.calculate_npv(
            projected_revenues=[1_000_000] * 3,
            royalty_rate=0.04,
            discount_rate=0.10,
        )
        rationale = RoyaltyReliefEngine.build_rationale(
            result, "technology", bsi_score=72
        )
        assert "Royalty Relief" in rationale
        assert "technology" in rationale.lower()
        assert "4.0%" in rationale
        assert "72/100" in rationale
        assert "Year 1" in rationale
