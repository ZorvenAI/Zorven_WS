"""
E2E test fixtures — wires discovery-agent-svc into orchestrator pipeline.

The discovery agent runs in-process: httpx_mock intercepts ExternalWrapper's
HTTP calls to discovery-agent-svc URLs and routes them to a mock handler
that implements the real discovery logic (query building, HTML cleaning,
response shaping).

Intelligence-agent-svc calls are NOT intercepted — ExternalWrapper's built-in
stub fallback handles them automatically.
"""

import json
import re
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.api.schemas import (
    AvailableManifest,
    DispatchRequest,
    ManifestData,
    ManifestNode,
    TenantContext,
)

# ---------------------------------------------------------------------------
# Discovery Agent Mock — implements the real discovery ExecuteResponse contract
# ---------------------------------------------------------------------------

MOCK_HTML_PAGES = {
    "https://example.com/market-analysis": (
        "<html><body><h1>Market Analysis</h1>"
        "<p>The brand equity market shows strong growth in Q4.</p>"
        "<script>track();</script></body></html>"
    ),
    "https://example.com/industry-report": (
        "<html><body><h1>Industry Report</h1>"
        "<p>Financial benchmarks indicate premium brand positioning.</p>"
        "<nav>Menu</nav></body></html>"
    ),
    "https://example.com/competitive-intel": (
        "<html><body><h1>Competitive Intelligence</h1>"
        "<p>SWOT analysis reveals strong market positioning.</p>"
        "</body></html>"
    ),
}


def _build_discovery_response(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Build a realistic discovery-agent-svc ExecuteResponse.

    Implements the same logic as DiscoveryExecutor:
    1. Build query from input_prompt + config.focus
    2. Return stub search results as sources
    3. Clean HTML to extract findings
    4. Build recommendations
    """
    input_prompt = payload.get("input_prompt", "")
    config = payload.get("config", {})
    focus = config.get("focus", "")

    # Build query (matches discovery_executor._build_query)
    parts = [input_prompt]
    if focus:
        focus_terms = [t.strip() for t in focus.split(",") if t.strip()]
        parts.extend(focus_terms)
    query = " ".join(parts)

    # Mock search results (matches SearchEngine._search_stub)
    sources = [
        {
            "type": "web",
            "title": f"Market Analysis: {query[:40]}",
            "url": "https://example.com/market-analysis",
        },
        {
            "type": "web",
            "title": f"Industry Report: {query[:40]}",
            "url": "https://example.com/industry-report",
        },
        {
            "type": "web",
            "title": f"Competitive Intel: {query[:40]}",
            "url": "https://example.com/competitive-intel",
        },
    ]

    # Findings from "cleaned" HTML (simulating DataCleaner output)
    findings = [
        "The brand equity market shows strong growth in Q4.",
        "Financial benchmarks indicate premium brand positioning.",
        "SWOT analysis reveals strong market positioning.",
    ]

    recommendations = [
        f"Review the {len(findings)} findings for actionable insights.",
        "Cross-reference web sources with internal data for validation.",
    ]

    raw_context = (
        "# Market Analysis\n\nThe brand equity market shows strong growth in Q4.\n\n"
        "---\n\n"
        "# Industry Report\n\n"
        "Financial benchmarks indicate premium brand positioning.\n\n"
        "---\n\n"
        "# Competitive Intelligence\n\nSWOT analysis reveals strong market positioning."
    )

    return {
        "query": query,
        "sources": sources,
        "findings": findings,
        "recommendations": recommendations,
        "raw_context": raw_context,
    }


# ---------------------------------------------------------------------------
# Seed manifest definitions (matching seed_manifests.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def brand_analysis_manifest() -> ManifestData:
    """brand-analysis seed manifest."""
    return ManifestData(
        nodes=[
            ManifestNode(id="intent_router", type="internal", handler="RouterNode"),
            ManifestNode(
                id="market_research",
                type="external",
                url="http://discovery-agent-svc:8020/v1/search",
                config={"focus": "market_trends,competitors"},
            ),
            ManifestNode(
                id="brand_strategist", type="internal", handler="StrategyNode"
            ),
            ManifestNode(id="report_generator", type="internal", handler="ReportNode"),
        ],
        edges=[
            ["intent_router", "market_research"],
            ["market_research", "brand_strategist"],
            ["brand_strategist", "report_generator"],
        ],
        global_config={"model": "gemini-2.0-flash", "temperature": 0.7},
    )


@pytest.fixture
def iso_brand_equity_manifest() -> ManifestData:
    """iso-brand-equity seed manifest."""
    return ManifestData(
        nodes=[
            ManifestNode(id="intent_router", type="internal", handler="RouterNode"),
            ManifestNode(
                id="web_research",
                type="external",
                url="http://discovery-agent-svc:8020/v1/search",
                config={"focus": "royalty_rates,market_trends,brand_rankings"},
            ),
            ManifestNode(
                id="valuation_logic",
                type="external",
                url="http://intelligence-agent-svc:8030/v1/execute",
                config={"focus": "brand_valuation,royalty_rates"},
            ),
            ManifestNode(id="manager", type="internal", handler="ManagerNode"),
        ],
        edges=[
            ["intent_router", "web_research"],
            ["web_research", "valuation_logic"],
            ["valuation_logic", "manager"],
        ],
        global_config={"model": "gemini-2.0-flash", "temperature": 0.3},
    )


@pytest.fixture
def competitor_audit_manifest() -> ManifestData:
    """competitor-audit seed manifest."""
    return ManifestData(
        nodes=[
            ManifestNode(id="intent_router", type="internal", handler="RouterNode"),
            ManifestNode(
                id="competitor_research",
                type="external",
                url="http://discovery-agent-svc:8020/v1/search",
                config={"focus": "competitors,market_share"},
            ),
            ManifestNode(
                id="gap_analyzer",
                type="external",
                url="http://intelligence-agent-svc:8030/v1/execute",
                config={"focus": "competitive_gaps"},
            ),
            ManifestNode(id="report_generator", type="internal", handler="ReportNode"),
        ],
        edges=[
            ["intent_router", "competitor_research"],
            ["competitor_research", "gap_analyzer"],
            ["gap_analyzer", "report_generator"],
        ],
        global_config={"model": "gemini-2.0-flash", "temperature": 0.5},
    )


@pytest.fixture
def content_strategy_manifest() -> ManifestData:
    """content-strategy seed manifest (all internal, no external calls)."""
    return ManifestData(
        nodes=[
            ManifestNode(id="intent_router", type="internal", handler="RouterNode"),
            ManifestNode(
                id="audience_analyzer", type="internal", handler="AudienceNode"
            ),
            ManifestNode(id="content_planner", type="internal", handler="PlannerNode"),
            ManifestNode(
                id="calendar_builder", type="internal", handler="CalendarNode"
            ),
        ],
        edges=[
            ["intent_router", "audience_analyzer"],
            ["audience_analyzer", "content_planner"],
            ["content_planner", "calendar_builder"],
        ],
        global_config={"model": "gemini-2.0-flash", "temperature": 0.7},
    )


# ---------------------------------------------------------------------------
# pytest-httpx configuration — apply to all E2E tests
# ---------------------------------------------------------------------------


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Allow unused httpx_mock callbacks and reusable responses for all E2E tests."""
    marker = pytest.mark.httpx_mock(
        assert_all_responses_were_requested=False,
        can_send_already_matched_responses=True,
    )
    for item in items:
        item.add_marker(marker)


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_discovery_service(httpx_mock):
    """
    Intercept ExternalWrapper HTTP calls to discovery-agent-svc.

    Routes requests through the in-process discovery handler that returns
    realistic ExecuteResponse data with findings, sources, and recommendations.
    """
    captured_requests: list[dict[str, Any]] = []

    def discovery_callback(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured_requests.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "payload": payload,
            }
        )
        response_data = _build_discovery_response(payload)
        return httpx.Response(status_code=200, json=response_data)

    httpx_mock.add_callback(
        discovery_callback,
        url=re.compile(r"http://discovery-agent-svc:8020/.*"),
        method="POST",
        is_reusable=True,
    )

    # Also register a stub for intelligence-agent-svc (not implemented yet)
    # ExternalWrapper catches the error and returns stub data, but pytest-httpx
    # needs to know about the request to avoid teardown assertion errors
    def intelligence_stub(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "status": "stub",
                "findings": ["Stub: intelligence analysis pending."],
                "recommendations": ["Deploy intelligence-agent-svc for real analysis."],
            },
        )

    httpx_mock.add_callback(
        intelligence_stub,
        url=re.compile(r"http://intelligence-agent-svc:8030/.*"),
        method="POST",
        is_reusable=True,
    )

    return captured_requests


@pytest.fixture
def mock_callback_server(httpx_mock):
    """
    Capture all PATCH callbacks from CallbackClient.

    Returns a list that accumulates callback payloads in order.
    """
    callbacks: list[dict[str, Any]] = []

    def callback_handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        callbacks.append(payload)
        return httpx.Response(status_code=200, json={"status": "ok"})

    httpx_mock.add_callback(
        callback_handler,
        url=re.compile(r"http://backend:8001/.*"),
        method="PATCH",
    )

    return callbacks


@pytest.fixture
def mock_redis_cancel():
    """Patch Redis to return 'not cancelled' for all cancel checks."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # not cancelled

    with patch(
        "app.services.job_executor.get_redis", new_callable=AsyncMock
    ) as mock_get_redis:
        mock_get_redis.return_value = mock_redis
        yield mock_redis


# ---------------------------------------------------------------------------
# Dispatch request factory
# ---------------------------------------------------------------------------


def make_dispatch_request(
    manifest: ManifestData,
    input_prompt: str = "Analyze brand positioning for Acme Corp",
    tenant_id: str = "1",
    job_id: str = "e2e-test-job-001",
) -> DispatchRequest:
    """Build a DispatchRequest for E2E testing."""
    return DispatchRequest(
        job_id=job_id,
        manifest=manifest,
        input_prompt=input_prompt,
        input_context={"company_id": 42},
        tenant_context=TenantContext(
            tenant_id=tenant_id,
            gcs_raw_bucket=f"brand-automator/{tenant_id}/",
            gcs_processed_bucket=f"brand-automator-curated/{tenant_id}/",
            rag_data_store_id="ds-123",
        ),
        callback_url=(
            f"http://backend:8001/api/v1/orchestration/jobs/{job_id}/callback/"
        ),
    )


def _brand_analysis_manifest_data() -> dict:
    """brand-analysis manifest_data dict for auto-detect tests."""
    return {
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
        "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
    }


def make_auto_detect_request(
    input_prompt: str = "Analyze brand positioning for Acme Corp",
    job_id: str = "e2e-auto-detect-001",
) -> DispatchRequest:
    """Build a DispatchRequest with no manifest (auto-detect mode)."""
    return DispatchRequest(
        job_id=job_id,
        manifest=None,
        input_prompt=input_prompt,
        input_context={},
        tenant_context=TenantContext(tenant_id="1"),
        callback_url=(
            f"http://backend:8001/api/v1/orchestration/jobs/{job_id}/callback/"
        ),
        available_manifests=[
            AvailableManifest(
                pipeline_id="iso-brand-equity",
                name="ISO Brand Equity",
                description="ISO 10668 brand valuation",
                manifest_data={
                    "nodes": [
                        {
                            "id": "intent_router",
                            "type": "internal",
                            "handler": "RouterNode",
                        },
                        {
                            "id": "web_research",
                            "type": "external",
                            "url": "http://discovery-agent-svc:8020/v1/search",
                            "config": {
                                "focus": "royalty_rates,market_trends,brand_rankings"
                            },
                        },
                        {
                            "id": "valuation_logic",
                            "type": "external",
                            "url": "http://intelligence-agent-svc:8030/v1/execute",
                            "config": {"focus": "brand_valuation,royalty_rates"},
                        },
                        {"id": "manager", "type": "internal", "handler": "ManagerNode"},
                    ],
                    "edges": [
                        ["intent_router", "web_research"],
                        ["web_research", "valuation_logic"],
                        ["valuation_logic", "manager"],
                    ],
                    "global_config": {"model": "gemini-2.0-flash", "temperature": 0.3},
                },
            ),
            AvailableManifest(
                pipeline_id="brand-analysis",
                name="Brand Analysis",
                description="Brand positioning analysis",
                manifest_data=_brand_analysis_manifest_data(),
            ),
            AvailableManifest(
                pipeline_id="competitor-audit",
                name="Competitor Audit",
                description="Competitive gap analysis",
                manifest_data={
                    "nodes": [
                        {
                            "id": "intent_router",
                            "type": "internal",
                            "handler": "RouterNode",
                        },
                        {
                            "id": "competitor_research",
                            "type": "external",
                            "url": "http://discovery-agent-svc:8020/v1/search",
                            "config": {"focus": "competitors,market_share"},
                        },
                        {
                            "id": "gap_analyzer",
                            "type": "external",
                            "url": "http://intelligence-agent-svc:8030/v1/execute",
                            "config": {"focus": "competitive_gaps"},
                        },
                        {
                            "id": "report_generator",
                            "type": "internal",
                            "handler": "ReportNode",
                        },
                    ],
                    "edges": [
                        ["intent_router", "competitor_research"],
                        ["competitor_research", "gap_analyzer"],
                        ["gap_analyzer", "report_generator"],
                    ],
                    "global_config": {"model": "gemini-2.0-flash", "temperature": 0.5},
                },
            ),
            AvailableManifest(
                pipeline_id="general-chat",
                name="General Chat (RAG)",
                description="Conversational AI with knowledge base retrieval",
                manifest_data={
                    "nodes": [
                        {
                            "id": "default_agent",
                            "type": "internal",
                            "handler": "DefaultAgentNode",
                        }
                    ],
                    "edges": [],
                    "global_config": {},
                },
            ),
            AvailableManifest(
                pipeline_id="content-strategy",
                name="Content Strategy",
                description="Content calendar planning",
                manifest_data={
                    "nodes": [
                        {
                            "id": "intent_router",
                            "type": "internal",
                            "handler": "RouterNode",
                        },
                        {
                            "id": "audience_analyzer",
                            "type": "internal",
                            "handler": "AudienceNode",
                        },
                        {
                            "id": "content_planner",
                            "type": "internal",
                            "handler": "PlannerNode",
                        },
                        {
                            "id": "calendar_builder",
                            "type": "internal",
                            "handler": "CalendarNode",
                        },
                    ],
                    "edges": [
                        ["intent_router", "audience_analyzer"],
                        ["audience_analyzer", "content_planner"],
                        ["content_planner", "calendar_builder"],
                    ],
                    "global_config": {"model": "gemini-2.0-flash", "temperature": 0.7},
                },
            ),
        ],
    )
