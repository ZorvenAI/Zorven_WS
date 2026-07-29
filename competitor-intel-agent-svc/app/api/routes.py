"""
API routes for competitor-intel-agent-svc.

Endpoints:
  GET  /health        - Health check (no auth)
  POST /v1/execute    - Execute competitive intelligence (primary endpoint)
  POST /v1/analyze    - Alias for /v1/execute (alternative endpoint)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header

from app.api.auth import verify_service_token
from app.api.schemas import (
    CompetitorIntelligenceResponse,
    ExecuteRequest,
    HealthResponse,
)
from app.core.config import settings
from app.services.cia_executor import CIAExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor - initialized in main.py lifespan
executor: Optional[CIAExecutor] = None


async def _execute_analysis(
    request: ExecuteRequest,
    tenant_id: str,
) -> CompetitorIntelligenceResponse:
    """Core competitive intelligence execution logic."""
    if executor is not None:
        return await executor.execute(request, tenant_id)

    # Fallback stub when executor not initialized
    return CompetitorIntelligenceResponse(
        query=request.input_prompt,
        executive_summary=(
            f"Stub: Competitive intelligence pending for "
            f"'{request.input_prompt[:50]}'."
        ),
        findings=[
            f"Stub finding: Analysis pending for '{request.input_prompt[:50]}'.",
            "Deploy competitor-intel-agent-svc with API keys for real results.",
        ],
        recommendations=[
            "Configure CIA_ANTHROPIC_API_KEY for LLM synthesis.",
            "Configure CIA_TAVILY_API_KEY for web search.",
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
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY
    tavily_key = settings.TAVILY_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)
    has_tavily = bool(tavily_key and len(tavily_key) > 4)

    issues: list[str] = []
    if not has_anthropic:
        issues.append(
            "CIA_ANTHROPIC_API_KEY is missing — running in STUB MODE"
        )
    if not has_tavily:
        issues.append(
            "CIA_TAVILY_API_KEY is missing — web search disabled"
        )

    return {
        "service": "competitor-intel-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.LLM_MODEL,
        "keys_configured": {
            "CIA_ANTHROPIC_API_KEY": has_anthropic,
            "CIA_TAVILY_API_KEY": has_tavily,
        },
        "issues": issues,
        "executor_initialized": executor is not None,
    }


@router.post(
    "/v1/execute",
    response_model=CompetitorIntelligenceResponse,
    dependencies=[Depends(verify_service_token)],
)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> CompetitorIntelligenceResponse:
    """
    Execute a competitive intelligence operation.

    Accepts the same payload the orchestrator's ExternalWrapper sends.
    """
    return await _execute_analysis(request, x_tenant_id)


@router.post(
    "/v1/analyze",
    response_model=CompetitorIntelligenceResponse,
    dependencies=[Depends(verify_service_token)],
)
async def analyze(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> CompetitorIntelligenceResponse:
    """
    Alias for /v1/execute.

    Maintained for backward compatibility with legacy pipeline manifests
    that referenced http://competitor-intel-agent-svc/v1/analyze.
    """
    return await _execute_analysis(request, x_tenant_id)
