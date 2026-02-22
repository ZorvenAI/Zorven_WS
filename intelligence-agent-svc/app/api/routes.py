"""
Intelligence agent API routes.

Endpoints:
  GET  /health       — Health check
  POST /v1/execute   — Primary analysis dispatch (routes by config)
  POST /v1/iso-calc  — ISO 10668 brand valuation (Royalty Relief)
  POST /v1/analyze   — Competitive gap analysis
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Module-level executor — initialized in main.py lifespan
executor: Optional["IntelligenceExecutor"] = None  # noqa: F821


# ---------------------------------------------------------------------------
# Core execution helper
# ---------------------------------------------------------------------------


async def _execute_intelligence(
    request: ExecuteRequest,
    tenant_id: str,
) -> ExecuteResponse:
    """Core intelligence execution logic."""
    if executor is not None:
        return await executor.execute(request, tenant_id)

    # Fallback stub when executor not initialized
    return ExecuteResponse(
        findings=[
            f"Stub: intelligence analysis for '{request.input_prompt[:50]}' pending.",
        ],
        recommendations=[
            "Deploy intelligence-agent-svc with full configuration for real analysis.",
        ],
        analysis_type="stub",
        rationale="Executor not initialized — returning stub response.",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/v1/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """Execute an intelligence analysis (routes by config)."""
    logger.info("POST /v1/execute from tenant %s", x_tenant_id)
    return await _execute_intelligence(request, x_tenant_id)


@router.post("/v1/iso-calc", response_model=ExecuteResponse)
async def iso_calc(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """ISO 10668 brand valuation using Royalty Relief method."""
    logger.info("POST /v1/iso-calc from tenant %s", x_tenant_id)
    # Ensure config has method=royalty_relief
    if "method" not in request.config:
        request.config["method"] = "royalty_relief"
    return await _execute_intelligence(request, x_tenant_id)


@router.post("/v1/analyze", response_model=ExecuteResponse)
async def analyze(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """Competitive gap analysis from discovery findings."""
    logger.info("POST /v1/analyze from tenant %s", x_tenant_id)
    # Ensure config has analysis_type=competitive_gap
    if "analysis_type" not in request.config:
        request.config["analysis_type"] = "competitive_gap"
    return await _execute_intelligence(request, x_tenant_id)
