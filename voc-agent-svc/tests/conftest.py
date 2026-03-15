"""Shared test fixtures for the Voice of Customer Agent service."""

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
        "input_prompt": "Analyze customer feedback for our SaaS product",
        "input_context": {
            "company_name": "TestCorp",
            "sector": "SaaS",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "gcs_raw_bucket": "test-bucket/raw/",
            "gcs_processed_bucket": "test-bucket/processed/",
            "rag_data_store_id": "ds-test-123",
            "user_role": "EDITOR",
        },
        "config": {},
        "previous_outputs": {},
    }


@pytest.fixture
def valid_payload_with_upstream_outputs():
    """Payload with upstream MRA + CIA + APA + TCIA data."""
    return {
        "input_prompt": "Analyze customer feedback for EV charging market",
        "input_context": {
            "company_name": "ChargePoint",
            "sector": "EV Charging",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
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
                "competitors": [
                    {"name": "Tesla Supercharger", "market_position": "leader"},
                    {"name": "Blink Charging", "market_position": "challenger"},
                ],
                "positioning_gaps": [
                    {"dimension": "Rural coverage", "opportunity_score": 8},
                ],
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


# -- Mock Tavily Client --


@pytest.fixture
def mock_tavily_client():
    """Mock Tavily search client."""
    mock = AsyncMock()
    mock.search = AsyncMock(
        return_value=[
            {
                "title": "Customer Review",
                "url": "https://example.com/review",
                "content": "Great product with excellent support",
            }
        ]
    )
    return mock


# -- Mock Odoo RPC Client --


@pytest.fixture
def mock_odoo_client():
    """Mock Odoo RPC client."""
    mock = AsyncMock()
    mock.search_read = AsyncMock(return_value=[])
    mock.search_count = AsyncMock(return_value=0)
    mock.authenticate = AsyncMock(return_value=2)
    mock.fields_get = AsyncMock(return_value={})
    return mock


# -- Mock Feedback Registry --


@pytest.fixture
def mock_feedback_registry():
    """Mock FeedbackRegistry."""
    mock = AsyncMock()
    mock.add_feedback = AsyncMock()
    mock.get_feedback_count = AsyncMock(return_value=0)
    mock.get_recent_feedback = AsyncMock(return_value=[])
    mock.upsert_theme = AsyncMock()
    mock.get_theme = AsyncMock(return_value=None)
    mock.get_all_themes = AsyncMock(return_value={})
    mock.add_daily_sentiment = AsyncMock()
    mock.add_monthly_nps = AsyncMock()
    mock.get_nps_history = AsyncMock(return_value=[])
    mock.add_coverage_score = AsyncMock()
    mock.set_last_synthesis = AsyncMock()
    return mock


# -- Mock Redis Manager --


@pytest.fixture
def mock_redis_manager():
    """Mock RedisManager for tests needing Redis."""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.cache_result = AsyncMock()
    mock.check_rate_limit = AsyncMock(return_value=True)
    mock.check_idempotency = AsyncMock(return_value=True)
    mock.get_odoo_cache = AsyncMock(return_value=None)
    mock.set_odoo_cache = AsyncMock()
    mock.get_tenant_config = AsyncMock(return_value=None)
    mock.get_operating_mode = AsyncMock(return_value=None)
    mock.set_operating_mode = AsyncMock()
    mock.store_hash_lookup = AsyncMock()
    mock.get_hash_lookup = AsyncMock(return_value=None)
    mock.get_ingestion_mode = AsyncMock(return_value=None)
    mock.set_ingestion_mode = AsyncMock()
    mock._redis = None
    return mock
