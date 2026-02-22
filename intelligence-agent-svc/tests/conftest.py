"""Shared test fixtures for intelligence-agent-svc."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.logic.analysis.competitive_gap import CompetitiveGapAnalyzer
from app.logic.analysis.theme_analyzer import ThemeAnalyzer
from app.logic.iso_engine.bsi_calculator import BSICalculator
from app.logic.iso_engine.proxy_engine import ProxyEngine
from app.logic.iso_engine.royalty_relief import RoyaltyReliefEngine
from app.main import app
from app.services.intelligence_executor import IntelligenceExecutor


@pytest.fixture
async def client():
    """Async HTTP client for testing endpoints."""
    # Set up a mock executor for route tests
    executor = IntelligenceExecutor(
        royalty_engine=RoyaltyReliefEngine(),
        bsi_calculator=BSICalculator(proxy_engine=ProxyEngine()),
        proxy_engine=ProxyEngine(),
        gap_analyzer=CompetitiveGapAnalyzer(),
        theme_analyzer=ThemeAnalyzer(),
    )
    routes.executor = executor

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    routes.executor = None


@pytest.fixture
def valid_iso_calc_payload() -> dict[str, Any]:
    """ISO 10668 Royalty Relief request payload."""
    return {
        "input_prompt": "Calculate brand value for Acme Corp",
        "input_context": {
            "company_id": 42,
            "sector": "technology",
            "base_revenue": 5_000_000,
            "growth_rate": 0.08,
        },
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
        },
        "config": {
            "method": "royalty_relief",
            "horizon_years": 5,
        },
        "previous_outputs": {
            "web_research": {
                "findings": [
                    "Market shows 5% growth",
                    "Royalty rates range 3-5%",
                ],
                "sources": [
                    {
                        "type": "web",
                        "title": "Market Report",
                        "url": "https://example.com",
                    }
                ],
            }
        },
    }


@pytest.fixture
def valid_gap_analysis_payload() -> dict[str, Any]:
    """Competitive gap analysis request payload."""
    return {
        "input_prompt": "Analyze competitive gaps for Acme Corp",
        "input_context": {},
        "config": {"analysis_type": "competitive_gap"},
        "previous_outputs": {
            "competitor_research": {
                "findings": [
                    "Competitor A is the market leader with strong brand recognition",
                    "Gap in digital presence and online engagement",
                    "Competitor B has innovative product development pipeline",
                    "Declining market share in the premium segment",
                ],
            }
        },
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Default tenant headers for test requests."""
    return {"X-Tenant-ID": "test-tenant"}


@pytest.fixture
def mock_redis_manager() -> AsyncMock:
    """Mock RedisManager that returns None for all cache operations."""
    manager = AsyncMock()
    manager.check_rate_limit.return_value = True
    manager.get_cached_result.return_value = None
    manager.get_benchmarks.return_value = None
    manager.get_wacc.return_value = None
    manager.set_cached_result.return_value = None
    manager.close.return_value = None
    return manager


@pytest.fixture
def mock_executor() -> IntelligenceExecutor:
    """IntelligenceExecutor with all real logic engines (no external deps)."""
    return IntelligenceExecutor(
        royalty_engine=RoyaltyReliefEngine(),
        bsi_calculator=BSICalculator(proxy_engine=ProxyEngine()),
        proxy_engine=ProxyEngine(),
        gap_analyzer=CompetitiveGapAnalyzer(),
        theme_analyzer=ThemeAnalyzer(),
    )
