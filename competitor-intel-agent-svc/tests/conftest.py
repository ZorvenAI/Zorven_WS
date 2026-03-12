"""Shared test fixtures for competitor-intel-agent-svc."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_execute_payload() -> dict[str, Any]:
    """
    A valid ExecuteRequest payload matching what the orchestrator's
    ExternalWrapper sends to external agent services.
    """
    return {
        "input_prompt": "Identify and profile competitors for Acme AI Tools",
        "input_context": {"company_id": 42, "job_id": "test-job-123"},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "config": {"focus": "competitor_profiling,swot,benchmarking,positioning"},
        "previous_outputs": {},
    }


@pytest.fixture
def valid_payload_with_mra_outputs() -> dict[str, Any]:
    """Payload with upstream MRA outputs for combined pipeline tests."""
    return {
        "input_prompt": "Analyze competitors in the AI brand tools market",
        "input_context": {"company_id": 42, "job_id": "test-job-456"},
        "tenant_context": {"tenant_id": "1"},
        "config": {"focus": "competitor_profiling,swot"},
        "previous_outputs": {
            "market_research": {
                "query": "AI brand tools market",
                "market_overview": "The AI brand tools market is growing rapidly.",
                "market_sizing": {
                    "tam": {"value": "$50B", "methodology": "top-down"},
                    "sam": {"value": "$12B"},
                    "som": {"value": "$1.5B"},
                },
                "competitive_landscape": [
                    {
                        "name": "BrandAI Corp",
                        "description": "Leader in AI branding",
                        "market_position": "leader",
                    },
                    {
                        "name": "SmartBrand Inc",
                        "description": "Challenger with strong growth",
                        "market_position": "challenger",
                    },
                ],
                "industry_trends": [
                    "AI adoption growing 25% YoY",
                    "Consolidation in brand tools space",
                ],
                "sources": [
                    {"type": "web", "title": "Market Report", "url": "https://example.com/report"}
                ],
                "findings": ["Market valued at $50B"],
                "recommendations": ["Focus on enterprise segment"],
                "confidence_score": 0.85,
            }
        },
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Headers with X-Tenant-ID for authenticated requests."""
    return {"X-Tenant-ID": "test-tenant"}
