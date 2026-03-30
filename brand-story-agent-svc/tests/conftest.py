"""Shared test fixtures for the Brand Story Agent service."""

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
        "input_prompt": "Create a brand story for our sustainable fashion brand",
        "input_context": {
            "company_name": "EcoThread",
            "sector": "Fashion",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "EcoThread",
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
    """Payload with upstream WF1 + BPA + BPV + NTA + BAA data."""
    return {
        "input_prompt": "Craft the brand story for our EV charging network",
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
                "confidence_score": 0.82,
            },
            "brand_personality": {
                "aaker_profile": {
                    "dimensions": [
                        {"dimension": "Competence", "score": 85},
                    ],
                    "primary_dimension": "Competence",
                },
                "archetype": {"primary": {"name": "Hero"}},
                "values_hierarchy": {"core": [{"name": "Reliability"}]},
            },
            "brand_architecture": {
                "recommendation": {"recommended_model": "branded_house"},
                "hierarchy": {
                    "root": {"name": "ChargePoint", "type": "master"},
                    "total_depth": 2,
                },
            },
            "brand_naming": {
                "naming_brief": {
                    "recommended_name": "VoltRide",
                    "recommended_tagline": "Powering every mile",
                },
                "name_candidates": [
                    {"name": "VoltRide", "scores": {"overall": 88}},
                ],
                "taglines": [
                    {"tagline": "Powering every mile", "name": "VoltRide"},
                ],
                "confidence_score": 0.85,
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
    mock.save_story = AsyncMock()
    mock.get_story = AsyncMock(return_value=None)
    mock._redis = None
    return mock


# -- Mock Context Loader --


@pytest.fixture
def mock_context_loader():
    """Mock BSAContextLoader with prerequisite data."""
    mock = AsyncMock()
    mock.load_wf1 = AsyncMock(return_value={"discoveries": True})
    mock.load_bpa = AsyncMock(
        return_value={"recommended_positioning": {"statement": "Test"}}
    )
    mock.load_bpv = AsyncMock(
        return_value={"archetype": {"primary": {"name": "Hero"}}}
    )
    mock.load_nta = AsyncMock(
        return_value={"naming_brief": {"recommended_name": "TestBrand"}}
    )
    mock.load_company = AsyncMock(return_value={"name": "TestCo"})
    mock.load_all = AsyncMock(
        return_value={
            "wf1": {"discoveries": True},
            "bpa": {"recommended_positioning": {"statement": "Test"}},
            "bpv": {"archetype": {"primary": {"name": "Hero"}}},
            "nta": {"naming_brief": {"recommended_name": "TestBrand"}},
            "company": {"name": "TestCo"},
        }
    )
    return mock


# -- Mock GCS Client --


@pytest.fixture
def mock_gcs_client():
    """Mock GCSClient for tests."""
    mock = AsyncMock()
    mock.upload_narrative = AsyncMock(return_value="gs://test-bucket/test-path.json")
    mock.download_narrative = AsyncMock(return_value=None)
    mock.enabled = False
    return mock
