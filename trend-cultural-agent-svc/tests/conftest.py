"""Shared test fixtures for the Trend & Cultural Insights Agent service.

Kafka mocked at import time via sys.modules patching.
Redis mocked via AsyncMock. Anthropic stubbed when API key absent.
"""

import json
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

# ── Kafka mock at import time ──
# Prevents aiokafka from being imported (no real broker needed for unit tests).
_kafka_mock = ModuleType("aiokafka")
_kafka_mock.AIOKafkaProducer = MagicMock  # type: ignore[attr-defined]
_kafka_mock.AIOKafkaConsumer = MagicMock  # type: ignore[attr-defined]
sys.modules.setdefault("aiokafka", _kafka_mock)

from app.main import app  # noqa: E402


# ── Async HTTP client ──


@pytest.fixture
async def async_client():
    """Async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Auth headers ──


@pytest.fixture
def service_token_headers():
    """Headers with valid X-Service-Token and X-Tenant-ID."""
    return {
        "X-Service-Token": "dev-service-token",
        "X-Tenant-ID": "test-tenant",
    }


@pytest.fixture
def tenant_headers():
    """Tenant ID header only (no service token)."""
    return {"X-Tenant-ID": "test-tenant"}


# ── Payloads ──


@pytest.fixture
def valid_execute_payload():
    """Standard orchestrator dispatch payload for TCIA."""
    return {
        "input_prompt": "Analyze cultural trends in the EV charging industry",
        "input_context": {
            "company_name": "ChargePoint",
            "job_id": "test-job-001",
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
    """Payload with upstream MRA + CIA + APA data."""
    return {
        "input_prompt": "Analyze cultural trends in the EV charging market",
        "input_context": {
            "company_name": "ChargePoint",
            "job_id": "test-job-002",
        },
        "tenant_context": {
            "tenant_id": "test-tenant",
            "user_role": "EDITOR",
        },
        "config": {},
        "previous_outputs": {
            "market_research": {
                "market_overview": {
                    "industry": "EV Charging",
                    "summary": "The EV charging market is growing at 25% CAGR",
                },
                "market_sizing": {
                    "tam": "$50B",
                    "sam": "$15B",
                    "som": "$3B",
                },
                "industry_trends": [
                    "Fast charging adoption",
                    "Grid integration",
                ],
                "competitive_landscape": [
                    {
                        "name": "Tesla Supercharger",
                        "market_position": "leader",
                    },
                ],
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
                        "segment_label": "Urban EV Commuter",
                        "demographics": {"age_range": "25-40"},
                        "media_habits": {
                            "preferred_channels": ["twitter", "linkedin"],
                        },
                    },
                    {
                        "segment_label": "Fleet Manager",
                        "demographics": {"age_range": "35-55"},
                        "media_habits": {
                            "preferred_channels": ["linkedin"],
                        },
                    },
                ],
            },
        },
    }


# ── Mock Redis Manager ──


@pytest.fixture
def mock_redis():
    """AsyncMock for RedisManager."""
    mock = AsyncMock()
    mock.get_cached_result = AsyncMock(return_value=None)
    mock.cache_result = AsyncMock()
    mock.check_rate_limit = AsyncMock(return_value=True)
    mock.check_idempotency = AsyncMock(return_value=False)
    mock.set_idempotency = AsyncMock()
    mock.get_alert_count = AsyncMock(return_value=0)
    mock.increment_alert_count = AsyncMock(return_value=1)
    mock.get_last_scan = AsyncMock(return_value="")
    mock.set_last_scan = AsyncMock()
    mock.get_tenant_config = AsyncMock(return_value="90")
    mock.hset = AsyncMock()
    mock.hget = AsyncMock(return_value=None)
    mock.hgetall = AsyncMock(return_value={})
    mock.hdel = AsyncMock(return_value=0)
    mock.hlen = AsyncMock(return_value=0)
    mock.zadd = AsyncMock(return_value=0)
    mock.zrangebyscore = AsyncMock(return_value=[])
    mock.zremrangebyscore = AsyncMock(return_value=0)
    mock.expire = AsyncMock()
    mock.connect = AsyncMock()
    mock.close = AsyncMock()
    return mock


# ── Mock Tavily Client ──


@pytest.fixture
def mock_tavily():
    """Mock for TavilySearchClient.search returning structured data."""
    mock = AsyncMock()
    mock.search = AsyncMock(
        return_value=[
            {
                "title": "Emerging Trend: Sustainable EV Charging",
                "url": "https://example.com/ev-trend",
                "content": "New trends in #sustainable #charging are reshaping the EV industry.",
            },
            {
                "title": "Cultural Shift: Remote Work and EVs",
                "url": "https://example.com/remote-ev",
                "content": "The remote work movement is driving suburban EV adoption.",
            },
        ]
    )
    return mock


# ── Mock Anthropic Client ──


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic client returning configurable JSON responses."""
    mock_client = AsyncMock()

    def _create_response(data):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(data))]
        mock_msg.usage = MagicMock(input_tokens=200, output_tokens=400)
        return mock_msg

    mock_client.messages.create = AsyncMock(
        return_value=_create_response({"stub": True})
    )
    mock_client._create_response = _create_response
    return mock_client


# ── Mock GCS Client ──


@pytest.fixture
def mock_gcs():
    """Mock for GCSClient."""
    mock = AsyncMock()
    mock.upload_report = AsyncMock(
        return_value="gs://test-bucket/test-tenant/trend-reports/daily_scan/2026-03-13.json"
    )
    mock.download_report = AsyncMock(
        return_value={
            "executive_summary": "Test trend report",
            "scored_trends": [],
            "confidence_score": 0.85,
        }
    )
    mock._ensure_client = MagicMock(return_value=True)
    return mock


# ── Mock Kafka Producers ──


@pytest.fixture
def mock_trace_producer():
    """Mock TraceProducer."""
    mock = AsyncMock()
    mock.send_trace = AsyncMock()
    mock.send_step = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def mock_audit_producer():
    """Mock AuditProducer."""
    mock = AsyncMock()
    mock.send_event = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def mock_alert_producer():
    """Mock AlertProducer."""
    mock = AsyncMock()
    mock.send_alert = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


# ── Mock Event Emitter ──


@pytest.fixture
def mock_event_emitter():
    """Mock EventEmitter."""
    mock = AsyncMock()
    mock.emit = AsyncMock()
    return mock


# ── Mock Trend Registry ──


@pytest.fixture
def mock_trend_registry():
    """Mock TrendRegistry."""
    mock = AsyncMock()
    mock.upsert_trend = AsyncMock(return_value=None)
    mock.get_trend = AsyncMock(return_value=None)
    mock.get_all_trends = AsyncMock(return_value={})
    mock.delete_trend = AsyncMock(return_value=True)
    mock.trend_count = AsyncMock(return_value=0)
    mock.get_score_history = AsyncMock(return_value=[])
    mock.evict_expired_scores = AsyncMock(return_value=0)
    return mock
