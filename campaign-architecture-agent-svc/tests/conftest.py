"""Shared test fixtures for the Campaign Architecture Agent service."""

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
def auth_headers():
    """Headers with valid service token."""
    return {
        "X-Service-Token": "dev-service-token",
        "X-Tenant-ID": "test-tenant",
    }


@pytest.fixture
def sample_execute_request():
    """Valid ExecuteRequest JSON with budget."""
    return {
        "input_prompt": "Design a Meta Ads campaign for our SaaS product launch",
        "input_context": {
            "company_name": "AcmeSaaS",
            "sector": "B2B SaaS",
            "job_id": "test-job-123",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "AcmeSaaS",
            "gcs_raw_bucket": "test-bucket/raw/",
            "gcs_processed_bucket": "test-bucket/processed/",
            "rag_data_store_id": "",
            "user_role": "EDITOR",
        },
        "config": {"daily_budget": 500.0},
        "previous_outputs": {},
    }


@pytest.fixture
def sample_execute_request_with_context():
    """Payload with upstream WF1 + WF2 + BPA + Company data."""
    return {
        "input_prompt": "Build a full-funnel Meta campaign for our EV charging brand",
        "input_context": {
            "company_name": "ChargePoint",
            "sector": "EV Charging",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "company_name": "ChargePoint",
            "user_role": "EDITOR",
        },
        "config": {"daily_budget": 1000.0},
        "previous_outputs": {
            "market_research": {
                "market_overview": "EV charging market growing at 25% CAGR",
            },
            "competitor_intelligence": {
                "competitors": [
                    {"name": "Tesla Supercharger", "market_share": 0.30},
                ],
            },
            "audience_persona": {
                "personas": [
                    {"slug": "fleet-manager", "segment_label": "Fleet Manager"},
                ],
            },
            "brand_positioning": {
                "recommended_positioning": {
                    "statement": "The most reliable EV charging network",
                },
                "confidence_score": 0.82,
            },
        },
    }


# -- Mock Anthropic Client --


@pytest.fixture
def mock_anthropic_client():
    """Mock AnthropicClient returning configurable JSON responses."""
    mock_client = AsyncMock()
    mock_client.generate_json = AsyncMock(
        return_value={
            "blueprint": {
                "campaign_name": "Test Campaign",
                "campaign_objective": "AWARENESS",
                "daily_budget": 500.0,
                "ad_sets": [],
            },
            "funnel_map": {"stages": []},
            "targeting_specs": [],
            "placement_budget": {},
            "test_plan": {"tests": []},
            "kpi_targets": {},
            "performance_projections": {},
            "risk_assessment": {},
            "creative_briefs": [],
            "recommendations": [],
            "confidence_score": 0.85,
        }
    )
    return mock_client


# -- Mock Redis Manager --


@pytest.fixture
def mock_redis_manager():
    """Mock RedisManager for tests needing Redis."""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.cache_result = AsyncMock()
    mock.check_rate_limit = AsyncMock(return_value=True)
    mock.save_blueprint = AsyncMock()
    mock.get_blueprint = AsyncMock(return_value=None)
    mock.get_json = AsyncMock(return_value=None)
    mock.set_json = AsyncMock()
    mock._redis = None
    return mock


# -- Mock Kafka Producers --


@pytest.fixture
def mock_kafka_trace():
    """Mock TraceProducer."""
    mock = AsyncMock()
    mock.send_trace = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def mock_kafka_audit():
    """Mock AuditProducer."""
    mock = AsyncMock()
    mock.send_event = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


# -- Mock GCS Client --


@pytest.fixture
def mock_gcs_client():
    """Mock GCSClient for tests."""
    mock = AsyncMock()
    mock.upload_blueprint = AsyncMock(
        return_value="gs://test-bucket/caa/test-tenant/test-job/blueprint.json"
    )
    mock.download_blueprint = AsyncMock(return_value=None)
    mock.enabled = False
    return mock


# -- Mock Tavily Client --


@pytest.fixture
def mock_tavily_client():
    """Mock TavilyClient for tests."""
    mock = AsyncMock()
    mock.enabled = False
    mock.search_benchmarks = AsyncMock(
        return_value={
            "answer": "Industry CPM is $8-12",
            "results": [{"title": "Benchmark Report", "url": "https://example.com"}],
            "query": "test benchmarks",
        }
    )
    mock.search_competitor_ads = AsyncMock(
        return_value={
            "answer": "Competitors focus on video ads",
            "results": [],
            "sources": [],
        }
    )
    return mock


# -- Mock Context Loader --


@pytest.fixture
def mock_context_loader():
    """Mock CAAContextLoader with prerequisite data."""
    mock = AsyncMock()
    mock.load_wf1 = AsyncMock(return_value={"discoveries": True, "industry": "SaaS"})
    mock.load_bpa = AsyncMock(
        return_value={"recommended_positioning": {"statement": "Best SaaS"}}
    )
    mock.load_wf2_chain = AsyncMock(return_value={"bpv": {}, "nta": {}, "bsa": {}})
    mock.load_company = AsyncMock(
        return_value={"name": "AcmeSaaS", "industry": "B2B SaaS"}
    )
    mock.load_baa = AsyncMock(return_value=None)
    mock.load_odoo = AsyncMock(return_value=None)
    mock.load_rag_learnings = AsyncMock(return_value=None)
    mock.load_all = AsyncMock(
        return_value={
            "wf1": {"discoveries": True, "industry": "SaaS"},
            "bpa": {"recommended_positioning": {"statement": "Best SaaS"}},
            "wf2_chain": {"bpv": {}, "nta": {}, "bsa": {}},
            "company": {"name": "AcmeSaaS", "industry": "B2B SaaS"},
            "baa": None,
            "odoo": None,
            "rag": None,
        }
    )
    return mock


# -- Mock Event Emitter --


@pytest.fixture
def mock_event_emitter():
    """Mock EventEmitter for tests."""
    mock = AsyncMock()
    mock.emit = AsyncMock()
    return mock
