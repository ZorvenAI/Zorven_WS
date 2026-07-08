"""Shared test fixtures for the Audience Persona Agent service."""

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
        "input_prompt": "Create buyer personas for a B2B SaaS product",
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
def valid_payload_with_mra_outputs():
    """Payload with upstream MRA + CIA data."""
    return {
        "input_prompt": "Build buyer personas for EV charging market",
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
                "market_sizing": {
                    "tam": "$50B",
                    "sam": "$15B",
                    "som": "$3B",
                },
                "industry_trends": [
                    "Fast charging adoption",
                    "Grid integration",
                ],
                "competitive_landscape": "Fragmented with key players",
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
        },
    }


# ── Mock Anthropic Client ──


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client returning configurable JSON responses."""
    mock_client = AsyncMock()

    def _create_response(data: dict):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(data), type="text")]
        mock_msg.usage = MagicMock(input_tokens=200, output_tokens=400)
        return mock_msg

    mock_client.messages.create = AsyncMock(
        return_value=_create_response({"stub": True})
    )
    mock_client._create_response = _create_response
    return mock_client


# ── Mock Tavily Client ──


@pytest.fixture
def mock_tavily_client():
    """Mock Tavily search client."""
    mock = AsyncMock()
    mock.search = AsyncMock(
        return_value=MagicMock(
            results=[
                MagicMock(
                    title="Research Result",
                    url="https://example.com/result",
                    content="Relevant audience research data",
                )
            ]
        )
    )
    return mock


# ── Mock Odoo RPC Client ──


@pytest.fixture
def mock_odoo_client():
    """Mock Odoo RPC client."""
    mock = AsyncMock()
    mock.search_read = AsyncMock(return_value=[])
    mock.search_count = AsyncMock(return_value=0)
    mock.authenticate = AsyncMock(return_value=2)
    return mock


# ── Mock Persona Registry ──


@pytest.fixture
def mock_persona_registry():
    """Mock PersonaRegistry."""
    mock = AsyncMock()
    mock.upsert_persona = AsyncMock()
    mock.get_persona = AsyncMock(return_value=None)
    mock.get_all_personas = AsyncMock(return_value={})
    mock.delete_persona = AsyncMock(return_value=True)
    mock.persona_count = AsyncMock(return_value=0)
    return mock


# ── Mock Redis Manager ──


@pytest.fixture
def mock_redis_manager():
    """Mock RedisManager for tests needing Redis."""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.set_cached_result = AsyncMock()
    mock.check_rate_limit = AsyncMock(return_value=True)
    mock.check_idempotency = AsyncMock(return_value=True)
    mock.set_odoo_survey_cache = AsyncMock()
    mock.get_odoo_survey_cache = AsyncMock(return_value=None)
    mock.set_odoo_crm_cache = AsyncMock()
    mock.get_odoo_crm_cache = AsyncMock(return_value=None)
    return mock
