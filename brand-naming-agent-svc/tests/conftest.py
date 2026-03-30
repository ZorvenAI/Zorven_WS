"""Shared test fixtures for the Naming & Tagline Agent service."""

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
        "input_prompt": "Generate brand names for our tech startup",
        "input_context": {
            "company_name": "TestCorp",
            "sector": "Technology",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "TestCorp",
            "gcs_raw_bucket": "test-bucket/raw/",
            "gcs_processed_bucket": "test-bucket/processed/",
            "rag_data_store_id": "ds-test-123",
            "user_role": "EDITOR",
        },
        "config": {},
        "previous_outputs": {},
    }


@pytest.fixture
def valid_payload_with_context():
    """Payload with upstream WF1 + BPA + BPV + BAA data."""
    return {
        "input_prompt": "Create brand name candidates for our EV charging network",
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
            },
            "audience_persona": {
                "personas": [
                    {
                        "slug": "fleet-manager",
                        "segment_label": "Fleet Manager",
                        "pain_points": ["Charging downtime"],
                    },
                ],
            },
            "voice_of_customer": {
                "sentiment": {"positive": 65, "neutral": 25, "negative": 10},
                "themes": ["reliability", "speed"],
            },
            "brand_positioning": {
                "recommended_positioning": {
                    "statement": "The most reliable EV charging network",
                    "framework_used": "classic",
                },
                "differentiation": {
                    "pods": [{"attribute": "Reliability"}],
                },
                "confidence_score": 0.82,
            },
            "brand_personality": {
                "aaker_profile": {
                    "dimensions": [
                        {"dimension": "Competence", "score": 85},
                        {"dimension": "Sincerity", "score": 60},
                    ],
                    "primary_dimension": "Competence",
                },
                "archetype": {"primary": {"name": "Hero"}},
                "values_hierarchy": {"core": [{"name": "Reliability"}]},
            },
            "brand_architecture": {
                "recommendation": {
                    "recommended_model": "branded_house",
                },
                "hierarchy": {
                    "root": {"name": "ChargePoint", "type": "master"},
                    "total_depth": 2,
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
    mock.save_naming = AsyncMock()
    mock.get_naming = AsyncMock(return_value=None)
    mock._redis = None
    return mock


# -- Mock Context Loader --


@pytest.fixture
def mock_context_loader():
    """Mock NTAContextLoader."""
    mock = AsyncMock()
    mock.load_wf1 = AsyncMock(return_value=None)
    mock.load_bpa = AsyncMock(return_value=None)
    mock.load_bpv = AsyncMock(return_value=None)
    mock.load_company = AsyncMock(return_value=None)
    mock.load_all = AsyncMock(
        return_value={"wf1": None, "bpa": None, "bpv": None, "company": None}
    )
    return mock
