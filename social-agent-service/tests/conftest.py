"""Shared test fixtures."""

from __future__ import annotations

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
    """A valid ExecuteRequest payload matching orchestrator's ExternalWrapper."""
    return {
        "input_prompt": "Promote our latest blog about Tesla sustainability",
        "input_context": {"company_id": 42, "job_id": "job-123", "user_id": 1},
        "tenant_context": {
            "tenant_id": "test-tenant",
            "gcs_raw_bucket": "brand-automator/test-tenant/",
            "gcs_processed_bucket": "brand-automator-curated/test-tenant/",
            "rag_data_store_id": "",
        },
        "config": {
            "platforms": ["linkedin", "twitter"],
        },
        "previous_outputs": {
            "blog_author": {
                "blog_content": (
                    "# Tesla's Sustainability Strategy\n\n"
                    "Tesla is leading the charge in sustainable "
                    "transportation with its electric vehicles and "
                    "solar energy products. The company's mission to "
                    "accelerate the world's transition to sustainable "
                    "energy is reflected in every aspect of its operations.\n\n"
                    "## Key Initiatives\n\n"
                    "- Electric vehicle manufacturing\n"
                    "- Solar roof and Powerwall\n"
                    "- Gigafactory renewable energy\n"
                ),
                "seo_meta": {
                    "title": "Tesla's Sustainability Strategy",
                    "description": "An analysis of Tesla's sustainability efforts",
                    "keywords": ["Tesla", "sustainability", "EV", "solar"],
                    "slug": "tesla-sustainability-strategy",
                },
                "gcs_uri": "gs://bucket/test/blogs/tesla-sustainability.md",
                "word_count": 150,
            },
        },
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    return {"X-Tenant-ID": "test-tenant"}


@pytest.fixture
def sample_blog_content() -> str:
    return (
        "# Tesla's Sustainability Strategy\n\n"
        "Tesla is leading the charge in sustainable transportation "
        "with its electric vehicles and solar energy products.\n\n"
        "## Key Initiatives\n\n"
        "- Electric vehicle manufacturing\n"
        "- Solar roof and Powerwall\n"
        "- Gigafactory renewable energy\n"
    )


@pytest.fixture
def sample_brand_persona() -> dict[str, Any]:
    return {
        "name": "TestBrand",
        "industry": "Technology",
        "brand_voice": "professional",
        "target_audience": "tech professionals",
        "vision_statement": "Making tech accessible",
        "values": ["innovation", "sustainability"],
        "positioning_statement": "Leading tech brand",
        "demographics": "25-45 professionals",
        "psychographics": "Early adopters",
        "pain_points": ["complexity", "cost"],
    }
