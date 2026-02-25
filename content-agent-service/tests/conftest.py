"""Shared test fixtures for content-agent-svc."""

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
        "input_prompt": "Write a blog about Tesla's sustainability strategy",
        "input_context": {"company_id": 42, "job_id": "job-123"},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "config": {"output_format": "markdown"},
        "previous_outputs": {
            "web_research": {
                "query": "Tesla sustainability strategy",
                "sources": [
                    {
                        "type": "web",
                        "title": "Tesla Impact Report",
                        "url": "https://example.com/tesla-impact",
                    },
                    {
                        "type": "web",
                        "title": "EV Market Trends",
                        "url": "https://example.com/ev-trends",
                    },
                ],
                "findings": [
                    "Tesla reduced manufacturing emissions by 20% in 2024.",
                    "The EV market is expected to grow 25% annually.",
                    "Tesla's Gigafactories use 70% renewable energy.",
                ],
                "recommendations": [
                    "Highlight sustainability metrics in brand communications.",
                ],
                "raw_context": (
                    "Tesla's 2024 Impact Report shows significant progress "
                    "in sustainability. Manufacturing emissions decreased 20%. "
                    "Gigafactories now run on 70% renewable energy sources."
                ),
            }
        },
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Headers with X-Tenant-ID for authenticated requests."""
    return {"X-Tenant-ID": "test-tenant"}


@pytest.fixture
def sample_research_data() -> dict[str, Any]:
    """Sample web_research output from discovery-agent-svc."""
    return {
        "query": "Tesla sustainability strategy",
        "sources": [
            {
                "type": "web",
                "title": "Tesla Impact Report",
                "url": "https://example.com/tesla-impact",
            },
            {
                "type": "web",
                "title": "EV Market Trends",
                "url": "https://example.com/ev-trends",
            },
        ],
        "findings": [
            "Tesla reduced manufacturing emissions by 20% in 2024.",
            "The EV market is expected to grow 25% annually.",
        ],
        "recommendations": [
            "Highlight sustainability metrics in brand communications.",
        ],
        "raw_context": (
            "Tesla's 2024 Impact Report shows significant progress "
            "in sustainability."
        ),
    }


@pytest.fixture
def sample_brand_persona() -> dict[str, Any]:
    """Sample brand persona from core-api."""
    return {
        "name": "Tesla",
        "industry": "Electric Vehicles",
        "brand_voice": "innovative, forward-thinking, and data-driven",
        "target_audience": "environmentally conscious professionals",
        "vision_statement": "Accelerate the transition to sustainable energy",
        "values": ["sustainability", "innovation", "excellence"],
        "positioning_statement": "Leading the charge in sustainable transportation",
        "demographics": "25-55, urban, tech-savvy",
        "psychographics": "Early adopters, environmentally conscious",
        "pain_points": ["range anxiety", "charging infrastructure"],
    }
