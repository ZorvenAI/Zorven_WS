"""
API routes for competitor-intel-agent-svc.

Endpoints:
  GET  /health        - Health check (no auth)
  POST /v1/execute    - Execute competitive intelligence (primary endpoint)
  POST /v1/analyze    - Alias for /v1/execute (alternative endpoint)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import (
    CompetitorIntelligenceResponse,
    ExecuteRequest,
    HealthResponse,
)
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


@router.post("/v1/execute", response_model=CompetitorIntelligenceResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> CompetitorIntelligenceResponse:
    """
    Execute a competitive intelligence operation.

    Accepts the same payload the orchestrator's ExternalWrapper sends.
    """
    return await _execute_analysis(request, x_tenant_id)


@router.post("/v1/analyze", response_model=CompetitorIntelligenceResponse)
async def analyze(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> CompetitorIntelligenceResponse:
    """
    Alias for /v1/execute.

    Seed manifests reference http://competitor-intel-agent-svc/v1/analyze,
    so this endpoint must exist alongside /v1/execute.
    """
    return await _execute_analysis(request, x_tenant_id)
