"""
API routes for discovery-agent-svc.

Endpoints:
  GET  /health       — Health check (no auth)
  POST /v1/execute   — Execute discovery (primary endpoint)
  POST /v1/search    — Alias for /v1/execute (matches seed manifest URLs)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from app.services.discovery_executor import DiscoveryExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor — initialized in main.py lifespan
executor: Optional[DiscoveryExecutor] = None


async def _execute_discovery(
    request: ExecuteRequest,
    tenant_id: str,
) -> ExecuteResponse:
    """Core discovery execution logic."""
    if executor is not None:
        return await executor.execute(request, tenant_id)

    # Fallback stub when executor not initialized
    focus = request.config.get("focus", "")
    focus_terms = [t.strip() for t in focus.split(",") if t.strip()]
    query_parts = [request.input_prompt]
    query_parts.extend(focus_terms)
    query = " ".join(query_parts)

    return ExecuteResponse(
        query=query,
        sources=[
            {
                "type": "web",
                "title": f"Stub result for: {request.input_prompt[:50]}",
                "url": "https://example.com/stub-result",
            }
        ],
        findings=[
            f"Stub finding: Analysis pending for '{request.input_prompt[:50]}'.",
            "Deploy discovery-agent-svc with Tavily API key for real results.",
        ],
        recommendations=[
            "Configure DISCOVERY_TAVILY_API_KEY for live web search.",
            "Re-run the pipeline after configuration.",
        ],
        raw_context=f"Stub context for query: {query}",
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/v1/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """
    Execute a discovery search and scrape operation.

    Accepts the same payload the orchestrator's ExternalWrapper sends.
    """
    return await _execute_discovery(request, x_tenant_id)


@router.post("/v1/search", response_model=ExecuteResponse)
async def search(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """
    Alias for /v1/execute.

    Seed manifests reference http://discovery-agent-svc/v1/search,
    so this endpoint must exist alongside /v1/execute.
    """
    return await _execute_discovery(request, x_tenant_id)
