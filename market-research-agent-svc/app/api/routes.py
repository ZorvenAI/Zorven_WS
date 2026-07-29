"""
API routes for market-research-agent-svc.

Endpoints:
  GET  /health              — Health check (no auth)
  GET  /health/diagnostics  — Detailed config diagnostics (no auth)
  POST /v1/execute          — Execute market research (primary endpoint)
  POST /v1/research         — Alias for /v1/execute (alternative endpoint)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, HealthResponse, MarketResearchResponse
from app.core.config import settings
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


@router.get("/health/diagnostics")
async def diagnostics() -> dict:
    """
    Detailed diagnostics showing which API keys are configured.

    Helps debug 30% confidence / stub mode issues in deployed environments.
    Does NOT expose actual key values — only whether they are set.
    """
    api_key = settings.ANTHROPIC_API_KEY
    tavily_key = settings.TAVILY_API_KEY
    gnews_key = settings.GNEWS_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)
    has_tavily = bool(tavily_key and len(tavily_key) > 4)
    has_gnews = bool(gnews_key and len(gnews_key) > 4)

    issues = []
    if not has_anthropic:
        issues.append("MRA_ANTHROPIC_API_KEY is missing — running in STUB MODE (all results will be 30% confidence)")
    if not has_tavily:
        issues.append("MRA_TAVILY_API_KEY is missing — web search disabled (raw_context will be empty, LLM synthesis skipped)")
    if not has_gnews:
        issues.append("MRA_GNEWS_API_KEY is missing — news data unavailable")

    return {
        "service": "market-research-agent-svc",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.LLM_MODEL,
        "keys_configured": {
            "MRA_ANTHROPIC_API_KEY": has_anthropic,
            "MRA_TAVILY_API_KEY": has_tavily,
            "MRA_GNEWS_API_KEY": has_gnews,
        },
        "issues": issues,
        "executor_initialized": executor is not None,
    }


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
