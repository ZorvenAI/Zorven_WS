"""
API routes for market-research-agent-svc.

Endpoints:
  GET  /health        — Health check (no auth)
  POST /v1/execute    — Execute market research (primary endpoint)
  POST /v1/research   — Alias for /v1/execute (matches seed manifest URLs)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, HealthResponse, MarketResearchResponse
from app.services.mra_executor import MRAExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor — initialized in main.py lifespan
executor: Optional[MRAExecutor] = None


async def _execute_research(
    request: ExecuteRequest,
    tenant_id: str,
) -> MarketResearchResponse:
    """Core market research execution logic."""
    if executor is not None:
        return await executor.execute(request, tenant_id)

    # Fallback stub when executor not initialized
    return MarketResearchResponse(
        query=request.input_prompt,
        market_overview=f"Stub: Market research pending for '{request.input_prompt[:50]}'.",
        findings=[
            f"Stub finding: Analysis pending for '{request.input_prompt[:50]}'.",
            "Deploy market-research-agent-svc with API keys for real results.",
        ],
        recommendations=[
            "Configure MRA_ANTHROPIC_API_KEY for LLM synthesis.",
            "Configure MRA_TAVILY_API_KEY for web search.",
            "Re-run the pipeline after configuration.",
        ],
        raw_context=f"Stub context for query: {request.input_prompt}",
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/v1/execute", response_model=MarketResearchResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> MarketResearchResponse:
    """
    Execute a market research operation.

    Accepts the same payload the orchestrator's ExternalWrapper sends.
    """
    return await _execute_research(request, x_tenant_id)


@router.post("/v1/research", response_model=MarketResearchResponse)
async def research(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> MarketResearchResponse:
    """
    Alias for /v1/execute.

    Seed manifests reference http://market-research-agent-svc/v1/research,
    so this endpoint must exist alongside /v1/execute.
    """
    return await _execute_research(request, x_tenant_id)
