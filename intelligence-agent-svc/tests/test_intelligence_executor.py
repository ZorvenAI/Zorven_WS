"""Tests for the IntelligenceExecutor orchestration service."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.schemas import ExecuteRequest
from app.logic.analysis.competitive_gap import CompetitiveGapAnalyzer
from app.logic.analysis.theme_analyzer import ThemeAnalyzer
from app.logic.iso_engine.bsi_calculator import BSICalculator
from app.logic.iso_engine.proxy_engine import ProxyEngine
from app.logic.iso_engine.royalty_relief import RoyaltyReliefEngine
from app.services.intelligence_executor import IntelligenceExecutor


class TestExecutorRouting:
    """Verify request routing based on config values."""

    def setup_method(self):
        self.executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(proxy_engine=ProxyEngine()),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
        )

    async def test_routes_to_iso_valuation(self):
        """method=royalty_relief → ISO valuation flow."""
        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            input_context={"sector": "technology", "base_revenue": 1_000_000},
            config={"method": "royalty_relief", "horizon_years": 3},
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.analysis_type == "iso_valuation"
        assert response.valuation is not None
        assert response.bsi is not None
        assert response.methodology == "royalty_relief"
        assert len(response.findings) > 0
        assert len(response.recommendations) > 0

    async def test_routes_to_gap_analysis(self):
        """analysis_type=competitive_gap → gap analysis flow."""
        request = ExecuteRequest(
            input_prompt="Analyze competitive gaps",
            config={"analysis_type": "competitive_gap"},
            previous_outputs={
                "research": {
                    "findings": [
                        "Strong market leader",
                        "Gap in digital strategy",
                    ]
                }
            },
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.analysis_type == "competitive_gap"
        assert response.gap_analysis is not None
        assert len(response.findings) > 0
        assert len(response.recommendations) > 0

    async def test_routes_to_general_analysis(self):
        """No specific config → general analysis fallback."""
        request = ExecuteRequest(
            input_prompt="Analyze the market",
            previous_outputs={
                "research": {
                    "findings": [
                        "Revenue growth observed",
                        "Brand awareness is strong",
                    ]
                }
            },
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.analysis_type == "general"
        assert len(response.findings) > 0


class TestISOValuationFlow:
    """Verify ISO 10668 valuation execution."""

    def setup_method(self):
        self.executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(proxy_engine=ProxyEngine()),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
        )

    async def test_valuation_with_user_revenue(self):
        """User-provided revenue should be used for NPV calc."""
        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            input_context={
                "sector": "technology",
                "projected_revenues": [1_000_000, 1_050_000, 1_102_500],
            },
            config={"method": "royalty_relief"},
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.valuation is not None
        assert response.valuation.brand_value_npv > 0
        assert response.valuation.horizon_years == 3

    async def test_valuation_with_base_revenue(self):
        """Base revenue + growth should be extrapolated."""
        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            input_context={
                "sector": "healthcare",
                "base_revenue": 2_000_000,
                "growth_rate": 0.10,
            },
            config={"method": "royalty_relief", "horizon_years": 5},
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.valuation is not None
        assert response.valuation.horizon_years == 5
        assert response.valuation.brand_value_npv > 0

    async def test_valuation_stub_revenues(self):
        """No revenue data → stub $10M base used."""
        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            config={"method": "royalty_relief"},
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.valuation is not None
        assert response.valuation.brand_value_npv > 0

    async def test_valuation_includes_bsi(self):
        """Valuation response includes BSI result."""
        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            input_context={"sector": "technology", "base_revenue": 1_000_000},
            config={"method": "royalty_relief"},
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.bsi is not None
        assert 0 <= response.bsi.score <= 100

    async def test_valuation_rationale_populated(self):
        """Rationale should contain methodology details."""
        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            input_context={"sector": "technology", "base_revenue": 1_000_000},
            config={"method": "royalty_relief"},
        )
        response = await self.executor.execute(request, "tenant-1")
        assert response.rationale
        assert "Royalty Relief" in response.rationale


class TestRateLimiting:
    """Verify rate limiting integration."""

    async def test_rate_limit_exceeded_raises_429(self):
        """Rate limit exceeded → HTTPException 429."""
        mock_redis = AsyncMock()
        mock_redis.check_rate_limit.return_value = False

        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=mock_redis,
        )

        request = ExecuteRequest(
            input_prompt="Test",
            config={"method": "royalty_relief"},
        )
        with pytest.raises(HTTPException) as exc_info:
            await executor.execute(request, "tenant-1")
        assert exc_info.value.status_code == 429

    async def test_rate_limit_allowed_proceeds(self):
        """Within rate limit → normal execution."""
        mock_redis = AsyncMock()
        mock_redis.check_rate_limit.return_value = True
        mock_redis.get_cached_result.return_value = None
        mock_redis.get_benchmarks.return_value = None
        mock_redis.get_wacc.return_value = None

        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=mock_redis,
        )

        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            config={"method": "royalty_relief"},
        )
        response = await executor.execute(request, "tenant-1")
        assert response.analysis_type == "iso_valuation"


class TestCaching:
    """Verify result caching."""

    async def test_cache_hit_returns_cached_result(self):
        """Cached result → returned without re-execution."""
        mock_redis = AsyncMock()
        mock_redis.check_rate_limit.return_value = True
        mock_redis.get_cached_result.return_value = {
            "findings": ["cached finding"],
            "recommendations": ["cached rec"],
            "analysis_type": "iso_valuation",
        }

        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=mock_redis,
        )

        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            config={"method": "royalty_relief"},
        )
        response = await executor.execute(request, "tenant-1")
        assert response.findings == ["cached finding"]

    async def test_cache_miss_executes_and_caches(self):
        """Cache miss → execute and cache result."""
        mock_redis = AsyncMock()
        mock_redis.check_rate_limit.return_value = True
        mock_redis.get_cached_result.return_value = None
        mock_redis.get_benchmarks.return_value = None
        mock_redis.get_wacc.return_value = None

        executor = IntelligenceExecutor(
            royalty_engine=RoyaltyReliefEngine(),
            bsi_calculator=BSICalculator(),
            proxy_engine=ProxyEngine(),
            gap_analyzer=CompetitiveGapAnalyzer(),
            theme_analyzer=ThemeAnalyzer(),
            redis_manager=mock_redis,
        )

        request = ExecuteRequest(
            input_prompt="Calculate brand value",
            config={"method": "royalty_relief"},
        )
        await executor.execute(request, "tenant-1")
        mock_redis.set_cached_result.assert_called_once()
