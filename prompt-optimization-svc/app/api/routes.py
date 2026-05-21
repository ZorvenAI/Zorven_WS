"""API routes for prompt-optimization-svc."""

import logging
from typing import Optional

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from app.services.health_checker import HealthChecker

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level health checker — initialized in main.py lifespan
health_checker: Optional[HealthChecker] = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check with dependency status."""
    if health_checker is not None:
        return await health_checker.check_all()
    return HealthResponse(status="unhealthy", dependencies=[])


@router.post("/v1/execute", response_model=ExecuteResponse, status_code=501)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> JSONResponse:
    """Execute prompt optimization (stub — implemented in EPIC-2+)."""
    return JSONResponse(
        status_code=501,
        content=ExecuteResponse().model_dump(),
    )


@router.post("/v1/optimize", response_model=ExecuteResponse, status_code=501)
async def optimize(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> JSONResponse:
    """Run GEPA optimization (stub — implemented in EPIC-5)."""
    return JSONResponse(
        status_code=501,
        content=ExecuteResponse().model_dump(),
    )
