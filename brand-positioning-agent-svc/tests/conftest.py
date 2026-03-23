"""Shared test fixtures for the Brand Positioning Agent service."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def service_token_headers():
    """Headers with valid service token."""
    return {
        "X-Service-Token": "dev-service-token",
        "X-Tenant-ID": "test-tenant",
    }


@pytest.fixture
def tenant_headers():
    """Tenant ID header."""
    return {"X-Tenant-ID": "test-tenant"}


@pytest.fixture
def valid_execute_payload():
    """Standard orchestrator dispatch payload."""
    return {
        "input_prompt": "Create a brand positioning strategy for our SaaS product",
        "input_context": {
            "company_name": "TestCorp",
            "sector": "SaaS",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "TestCorp",
            "gcs_raw_bucket": "test-bucket/raw/",
            "gcs_processed_bucket": "test-bucket/processed/",
            "rag_data_store_id": "ds-test-123",
            "user_role": "EDITOR",
        },
        "config": {
            "candidate_count": 3,
            "perceptual_maps": 3,
        },
        "previous_outputs": {},
    }


@pytest.fixture
def valid_payload_with_wf1_outputs():
    """Payload with upstream WF1 agent data."""
    return {
        "input_prompt": "Position our EV charging brand in the market",
        "input_context": {
            "company_name": "ChargePoint",
            "sector": "EV Charging",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "ChargePoint",
            "user_role": "EDITOR",
        },
        "config": {},
        "previous_outputs": {
            "market_research": {
                "market_overview": "The EV charging market is growing at 25% CAGR",
                "market_sizing": {"tam": "$50B", "sam": "$15B", "som": "$3B"},
                "industry_trends": ["Fast charging adoption", "Grid integration"],
            },
            "competitor_intelligence": {
                "competitors_analyzed": ["Tesla Supercharger", "Blink Charging"],
                "positioning_gaps": [
                    {"dimension": "Rural coverage", "opportunity_score": 8},
                ],
                "swot_analysis": {
                    "strengths": ["Wide network"],
                    "weaknesses": ["High pricing"],
                },
            },
            "audience_persona": {
                "personas": [
                    {
                        "slug": "fleet-manager",
                        "segment_label": "Fleet Manager",
                        "pain_points": ["Charging downtime", "Route planning"],
                    },
                    {
                        "slug": "ev-owner",
                        "segment_label": "EV Owner",
                        "pain_points": ["Long wait times", "Price unpredictability"],
                    },
                ],
            },
            "trend_cultural": {
                "scored_trends": [
                    {
                        "topic": "EV adoption acceleration",
                        "relevance_score": 85,
                    },
                ],
                "cultural_shifts": ["Sustainability consciousness"],
            },
            "voice_of_customer": {
                "voc_health_score": 72.5,
                "sentiment": {
                    "overall_sentiment": {
                        "positive": 0.65,
                        "neutral": 0.25,
                        "negative": 0.10,
                    },
                },
                "pain_point_priority_matrix": {
                    "pain_points": [
                        {
                            "name": "Charging speed",
                            "severity": 9,
                            "persona_impact": ["fleet-manager", "ev-owner"],
                        },
                        {
                            "name": "Station availability",
                            "severity": 8,
                            "persona_impact": ["ev-owner"],
                        },
                    ],
                },
                "themes": {
                    "themes": [
                        {"theme_name": "Reliability", "feedback_count": 150},
                    ],
                },
            },
        },
    }


# -- Mock Anthropic Client --


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client returning configurable JSON responses."""
    mock_client = AsyncMock()

    def _create_response(data: dict):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(data))]
        mock_msg.usage = MagicMock(input_tokens=200, output_tokens=400)
        return mock_msg

    mock_client.messages.create = AsyncMock(
        return_value=_create_response({"stub": True})
    )
    mock_client._create_response = _create_response
    return mock_client


# -- Mock Redis Manager --


@pytest.fixture
def mock_redis_manager():
    """Mock RedisManager for tests needing Redis."""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.cache_result = AsyncMock()
    mock.check_rate_limit = AsyncMock(return_value=True)
    mock.save_positioning = AsyncMock()
    mock.get_positioning = AsyncMock(return_value=None)
    mock.save_perceptual_map = AsyncMock()
    mock._redis = None
    return mock


# -- Mock WF1 Loader --


@pytest.fixture
def mock_wf1_loader():
    """Mock WF1ContextLoader."""
    mock = AsyncMock()
    mock.load = AsyncMock(return_value=None)
    return mock
