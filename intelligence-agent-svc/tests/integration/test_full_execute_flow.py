"""End-to-end integration tests with real Redis.

These tests require a running Redis instance on localhost:6379.
Run with: pytest tests/integration/ -v -m integration
"""

import pytest

from app.api.schemas import ExecuteRequest
from app.logic.analysis.competitive_gap import CompetitiveGapAnalyzer
from app.logic.analysis.theme_analyzer import ThemeAnalyzer
from app.logic.iso_engine.bsi_calculator import BSICalculator
from app.logic.iso_engine.proxy_engine import ProxyEngine
from app.logic.iso_engine.royalty_relief import RoyaltyReliefEngine
from app.services.intelligence_executor import IntelligenceExecutor


@pytest.mark.integration
class TestFullISOFlow:
    """End-to-end ISO valuation with real Redis caching."""

    async def test_iso_valuation_with_redis_caching(self, redis_manager):
        """Full ISO valuation flow with result caching."""
        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(proxy_engine=ProxyEngine()),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=redis_manager,
        )

        request = ExecuteRequest(
            input_prompt="Calculate brand value for Test Corp",
            input_context={
                "sector": "technology",
                "base_revenue": 5_000_000,
                "growth_rate": 0.08,
            },
            config={"method": "royalty_relief", "horizon_years": 5},
        )

        # First execution — cache miss
        response1 = await executor.execute(request, "integration-tenant")
        assert response1.analysis_type == "iso_valuation"
        assert response1.valuation is not None
        assert response1.valuation.brand_value_npv > 0

        # Second execution — cache hit (same result)
        response2 = await executor.execute(request, "integration-tenant")
        assert response2.findings == response1.findings

    async def test_rate_limiting_with_redis(self, redis_manager):
        """Rate limiting enforced via real Redis."""
        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=redis_manager,
        )

        request = ExecuteRequest(
            input_prompt="Rate limit test",
            config={"method": "royalty_relief"},
        )

        # Should succeed within rate limit
        response = await executor.execute(request, "rate-test-tenant")
        assert len(response.findings) > 0

    async def test_benchmark_caching(self, redis_manager):
        """Benchmark data cached and retrieved from Redis."""
        # Set benchmark
        await redis_manager.set_benchmarks(
            "technology", {"royalty_rate": 0.045, "source": "industry_report"}
        )

        # Get benchmark
        cached = await redis_manager.get_benchmarks("technology")
        assert cached is not None
        assert cached["royalty_rate"] == 0.045

    async def test_wacc_caching(self, redis_manager):
        """WACC cached and retrieved from Redis."""
        await redis_manager.set_wacc("us", 0.085)
        cached = await redis_manager.get_wacc("us")
        assert cached == pytest.approx(0.085)


@pytest.mark.integration
class TestFullGapAnalysisFlow:
    """End-to-end gap analysis with real Redis."""

    async def test_gap_analysis_with_caching(self, redis_manager):
        """Full gap analysis flow with result caching."""
        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=redis_manager,
        )

        request = ExecuteRequest(
            input_prompt="Analyze competitive gaps",
            config={"analysis_type": "competitive_gap"},
            previous_outputs={
                "research": {
                    "findings": [
                        "Market leader with strong brand",
                        "Gap in digital strategy",
                        "Declining loyalty scores",
                    ]
                }
            },
        )

        response = await executor.execute(request, "gap-tenant")
        assert response.analysis_type == "competitive_gap"
        assert response.gap_analysis is not None
        assert len(response.findings) > 0
