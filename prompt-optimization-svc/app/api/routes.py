"""API routes for prompt-optimization-svc."""

import logging
from typing import Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    PromptRegistrationRequest,
    PromptRegistrationResponse,
    SeedResponse,
)
from app.services.health_checker import HealthChecker
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies — initialized in main.py lifespan
health_checker: Optional[HealthChecker] = None
mlflow_registry: Optional[MLflowPromptRegistry] = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check with dependency status."""
    if health_checker is not None:
        return await health_checker.check_all()
    return HealthResponse(status="unhealthy", dependencies=[])


@router.post("/v1/prompts", response_model=PromptRegistrationResponse)
async def register_prompt(
    request: PromptRegistrationRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> PromptRegistrationResponse:
    """Register a prompt template in MLflow Prompt Registry."""
    if mlflow_registry is None:
        return PromptRegistrationResponse(
            name=request.name,
            version=1,
            status="registered",
            message="Prompt registered (MLflow not connected — stub mode)",
        )
    try:
        info = mlflow_registry.register_prompt(
            name=request.name,
            template=request.template,
            tags={**request.metadata, "state": "DRAFT"},
        )
        return PromptRegistrationResponse(
            name=info.name,
            version=info.version,
            status="registered",
        )
    except Exception as exc:
        logger.error("Failed to register prompt %s: %s", request.name, exc)
        return PromptRegistrationResponse(
            name=request.name,
            version=0,
            status="error",
            message=str(exc),
        )


@router.post("/v1/prompts/seed", response_model=SeedResponse)
async def seed_prompts() -> SeedResponse:
    """Seed the complete prompt catalog into MLflow."""
    if mlflow_registry is None:
        return SeedResponse(errors=1, details=["MLflow not connected"])
    from app.services.prompt_seeder import seed_prompt_catalog

    result = seed_prompt_catalog(mlflow_registry)
    return SeedResponse(
        created=result.created,
        skipped=result.skipped,
        errors=result.errors,
        details=result.details,
    )


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
