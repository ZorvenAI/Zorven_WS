"""Shared test fixtures for the Creative Generation Agent service."""

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
    """Standard orchestrator dispatch payload with campaign architecture context."""
    return {
        "input_prompt": "Generate ad creatives for our EV charging campaign",
        "input_context": {
            "company_name": "ChargePoint",
            "sector": "EV Charging",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "ChargePoint",
            "gcs_raw_bucket": "test-bucket/raw/",
            "gcs_processed_bucket": "test-bucket/processed/",
            "rag_data_store_id": "ds-test-123",
            "user_role": "EDITOR",
        },
        "config": {},
        "previous_outputs": {
            "campaign_architecture": {
                "campaign_blueprint": {
                    "campaign_name": "EV Charging Awareness",
                    "objective": "AWARENESS",
                },
                "ad_sets": [
                    {
                        "ad_set_name": "fleet-managers-tofu",
                        "persona_name": "Fleet Manager",
                        "funnel_stage": "tofu",
                        "creative_brief": {
                            "visual_direction": "Professional fleet imagery",
                            "copy_tone": "authoritative yet approachable",
                        },
                    },
                ],
                "confidence_score": 0.85,
            },
        },
    }


@pytest.fixture
def valid_payload_with_context():
    """Payload with full WF1 + WF2 + CAA previous_outputs."""
    return {
        "input_prompt": "Create ad creatives for our EV charging brand",
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
            "campaign_architecture": {
                "campaign_blueprint": {
                    "campaign_name": "EV Charging Awareness",
                    "objective": "AWARENESS",
                },
                "ad_sets": [
                    {
                        "ad_set_name": "fleet-managers-tofu",
                        "persona_name": "Fleet Manager",
                        "funnel_stage": "tofu",
                        "creative_brief": {
                            "visual_direction": "Professional fleet imagery",
                            "copy_tone": "authoritative yet approachable",
                        },
                    },
                ],
                "confidence_score": 0.85,
            },
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
            "brand_story": {
                "origin_story": {
                    "archetype_used": "Hero",
                    "versions": [
                        {"version_label": "short", "content": "Our story..."},
                    ],
                },
                "mission_vision": {
                    "mission": {"recommended": "Powering sustainable transport"},
                    "vision": {"recommended": "A world connected by clean energy"},
                },
                "confidence_score": 0.81,
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
    """Mock RedisManager for tests — fail-open behaviour."""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.cache_result = AsyncMock()
    mock.check_rate_limit = AsyncMock(return_value=True)
    mock._redis = None
    return mock


# -- Mock Context Loader --


@pytest.fixture
def mock_context_loader():
    """Mock CGAContextLoader with prerequisite data."""
    mock = AsyncMock()
    mock.load_caa = AsyncMock(
        return_value={
            "campaign_blueprint": {
                "campaign_name": "Test Campaign",
                "objective": "AWARENESS",
            },
            "ad_sets": [
                {
                    "ad_set_name": "test-tofu",
                    "persona_name": "Test Persona",
                    "funnel_stage": "tofu",
                },
            ],
        }
    )
    mock.load_wf1 = AsyncMock(return_value={"discoveries": True})
    mock.load_bpa = AsyncMock(
        return_value={"recommended_positioning": {"statement": "Test"}}
    )
    mock.load_bpv = AsyncMock(return_value={"archetype": {"primary": {"name": "Hero"}}})
    mock.load_nta = AsyncMock(
        return_value={"naming_brief": {"recommended_name": "TestBrand"}}
    )
    mock.load_bsa = AsyncMock(return_value={"origin_story": {"archetype_used": "Hero"}})
    mock.load_company = AsyncMock(return_value={"name": "TestCo"})
    mock.load_all = AsyncMock(
        return_value={
            "caa": {
                "campaign_blueprint": {
                    "campaign_name": "Test Campaign",
                    "objective": "AWARENESS",
                },
                "ad_sets": [],
            },
            "wf1": {"discoveries": True},
            "bpa": {"recommended_positioning": {"statement": "Test"}},
            "bpv": {"archetype": {"primary": {"name": "Hero"}}},
            "nta": {"naming_brief": {"recommended_name": "TestBrand"}},
            "bsa": {"origin_story": {"archetype_used": "Hero"}},
            "company": {"name": "TestCo"},
        }
    )
    return mock


# -- Mock GCS Client --


@pytest.fixture
def mock_gcs_client():
    """Mock GCSClient for tests."""
    mock = AsyncMock()
    mock.upload_image = AsyncMock(return_value="gs://test-bucket/images/test-image.png")
    mock.upload_package = AsyncMock(
        return_value="gs://test-bucket/packages/test-package.json"
    )
    mock.enabled = False
    return mock


# -- Mock Image Generation Client --


@pytest.fixture
def mock_image_gen_client():
    """Mock ImageGenClient for tests — returns stub generated images."""
    mock = AsyncMock()

    generated = MagicMock()
    generated.image_data = b"fake"
    generated.cost_usd = 0.065
    generated.provider = "stub"

    mock.generate = AsyncMock(return_value=generated)
    return mock
