"""
Shared integration test fixtures.

All integration tests run against live Docker containers started via
docker-compose.test.yml. Services run in stub mode (no real API keys).
"""

import uuid
from typing import Any

import httpx
import pytest
import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Service URLs — match docker-compose.test.yml port mappings
# ---------------------------------------------------------------------------

ORCHESTRATOR_URL = "http://localhost:18010"
DISCOVERY_URL = "http://localhost:18020"
INTELLIGENCE_URL = "http://localhost:18030"
REDIS_URL = "redis://localhost:16379"

# Auth tokens — match docker-compose.test.yml env vars
SERVICE_TOKEN = "test-service-token"
CALLBACK_TOKEN = "test-callback-token"


# ---------------------------------------------------------------------------
# HTTP client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def http_client():
    """Async HTTP client for integration tests."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture(autouse=True)
async def flush_intel_cache():
    """Flush the intelligence agent's result cache before each test.

    The intelligence agent caches results by (tenant_id, input_prompt, config).
    Without flushing, tests with similar payloads return stale cached results.
    Intelligence uses Redis DB 3 (mapped to localhost:16379).
    """
    r = aioredis.Redis.from_url(f"{REDIS_URL}/3")
    try:
        await r.flushdb()
    finally:
        await r.aclose()


# ---------------------------------------------------------------------------
# Auth header fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_headers() -> dict[str, str]:
    """Headers for orchestrator dispatch/cancel (X-Service-Token)."""
    return {
        "X-Service-Token": SERVICE_TOKEN,
        "Content-Type": "application/json",
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Headers for agent service calls (X-Tenant-ID)."""
    return {
        "X-Tenant-ID": "integration-test-tenant",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Payload factories
# ---------------------------------------------------------------------------


def make_job_id() -> str:
    """Generate a unique job ID for test isolation."""
    return f"integ-{uuid.uuid4().hex[:12]}"


def make_dispatch_payload(
    *,
    job_id: str | None = None,
    manifest: dict[str, Any] | None = None,
    input_prompt: str = "Analyze brand positioning for Acme Corp",
    available_manifests: list[dict[str, Any]] | None = None,
    callback_url: str = "http://host.docker.internal:9999/callback",
) -> dict[str, Any]:
    """Build a DispatchRequest payload matching _build_payload()."""
    payload: dict[str, Any] = {
        "job_id": job_id or make_job_id(),
        "manifest": manifest,
        "input_prompt": input_prompt,
        "input_context": {"company_id": 42},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "callback_url": callback_url,
    }
    if available_manifests is not None:
        payload["available_manifests"] = available_manifests
    return payload


def make_agent_payload(
    *,
    input_prompt: str = "Analyze brand positioning for Acme Corp",
    config: dict[str, Any] | None = None,
    previous_outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a payload matching ExternalWrapper's POST body to agent services."""
    return {
        "input_prompt": input_prompt,
        "input_context": {"company_id": 42},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "config": config or {},
        "previous_outputs": previous_outputs or {},
    }


# ---------------------------------------------------------------------------
# Seed manifest data (mirrors seed_manifests.py)
# ---------------------------------------------------------------------------

BRAND_ANALYSIS_MANIFEST: dict[str, Any] = {
    "nodes": [
        {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
        {
            "id": "market_research",
            "type": "external",
            "url": "http://discovery-agent-svc:8020/v1/search",
            "config": {"focus": "market_trends,competitors"},
        },
        {"id": "brand_strategist", "type": "internal", "handler": "StrategyNode"},
        {"id": "report_generator", "type": "internal", "handler": "ReportNode"},
    ],
    "edges": [
        ["intent_router", "market_research"],
        ["market_research", "brand_strategist"],
        ["brand_strategist", "report_generator"],
    ],
    "global_config": {"model": "gemini-3.5-flash", "temperature": 0.7},
}

ISO_BRAND_EQUITY_MANIFEST: dict[str, Any] = {
    "nodes": [
        {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
        {
            "id": "web_research",
            "type": "external",
            "url": "http://discovery-agent-svc:8020/v1/search",
            "config": {"focus": "royalty_rates,market_trends,brand_rankings"},
        },
        {
            "id": "valuation_logic",
            "type": "external",
            "url": "http://intelligence-agent-svc:8030/v1/iso-calc",
            "config": {"method": "royalty_relief", "horizon_years": 5},
        },
        {"id": "manager", "type": "internal", "handler": "ManagerNode"},
    ],
    "edges": [
        ["intent_router", "web_research"],
        ["web_research", "valuation_logic"],
        ["valuation_logic", "manager"],
    ],
    "global_config": {"model": "gemini-3.5-flash", "temperature": 0.3},
}

COMPETITOR_AUDIT_MANIFEST: dict[str, Any] = {
    "nodes": [
        {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
        {
            "id": "competitor_research",
            "type": "external",
            "url": "http://discovery-agent-svc:8020/v1/search",
            "config": {"focus": "competitors,market_share"},
        },
        {
            "id": "gap_analyzer",
            "type": "external",
            "url": "http://intelligence-agent-svc:8030/v1/analyze",
            "config": {"analysis_type": "competitive_gap"},
        },
        {"id": "report_generator", "type": "internal", "handler": "ReportNode"},
    ],
    "edges": [
        ["intent_router", "competitor_research"],
        ["competitor_research", "gap_analyzer"],
        ["gap_analyzer", "report_generator"],
    ],
    "global_config": {"model": "gemini-3.5-flash", "temperature": 0.5},
}

CONTENT_STRATEGY_MANIFEST: dict[str, Any] = {
    "nodes": [
        {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
        {"id": "audience_analyzer", "type": "internal", "handler": "AudienceNode"},
        {"id": "content_planner", "type": "internal", "handler": "PlannerNode"},
        {"id": "calendar_builder", "type": "internal", "handler": "CalendarNode"},
    ],
    "edges": [
        ["intent_router", "audience_analyzer"],
        ["audience_analyzer", "content_planner"],
        ["content_planner", "calendar_builder"],
    ],
    "global_config": {"model": "gemini-3.5-flash", "temperature": 0.7},
}

GENERAL_CHAT_MANIFEST: dict[str, Any] = {
    "nodes": [
        {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
        {"id": "manager", "type": "internal", "handler": "ManagerNode"},
    ],
    "edges": [
        ["intent_router", "manager"],
    ],
    "global_config": {"model": "gemini-3.5-flash", "temperature": 0.7},
}

ALL_AVAILABLE_MANIFESTS: list[dict[str, Any]] = [
    {
        "pipeline_id": "brand-analysis",
        "name": "Brand Analysis",
        "description": "Brand positioning analysis",
        "manifest_data": BRAND_ANALYSIS_MANIFEST,
    },
    {
        "pipeline_id": "iso-brand-equity",
        "name": "ISO Brand Equity",
        "description": "ISO 10668 brand valuation",
        "manifest_data": ISO_BRAND_EQUITY_MANIFEST,
    },
    {
        "pipeline_id": "competitor-audit",
        "name": "Competitor Audit",
        "description": "Competitive gap analysis",
        "manifest_data": COMPETITOR_AUDIT_MANIFEST,
    },
    {
        "pipeline_id": "content-strategy",
        "name": "Content Strategy",
        "description": "Content calendar planning",
        "manifest_data": CONTENT_STRATEGY_MANIFEST,
    },
    {
        "pipeline_id": "general-chat",
        "name": "General Chat",
        "description": "General-purpose document Q&A and conversation",
        "manifest_data": GENERAL_CHAT_MANIFEST,
    },
]
