"""API routes for prompt-optimization-svc."""

import logging
from typing import Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    ProductionPromptResponse,
    PromptDetailResponse,
    PromptListResponse,
    PromptMetadata,
    PromptRegistrationRequest,
    PromptRegistrationResponse,
    PromptSummary,
    PromptTransitionRequest,
    PromptTransitionResponse,
    SeedResponse,
)
from app.logic.lifecycle import (
    InvalidTransitionError,
    PromptLifecycleManager,
    PromptState,
)
from app.services.health_checker import HealthChecker
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies — initialized in main.py lifespan
health_checker: Optional[HealthChecker] = None
mlflow_registry: Optional[MLflowPromptRegistry] = None
lifecycle_manager: Optional[PromptLifecycleManager] = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check with dependency status."""
    if health_checker is not None:
        return await health_checker.check_all()
    return HealthResponse(status="unhealthy", dependencies=[])


@router.get("/v1/prompts", response_model=PromptListResponse)
async def list_prompts() -> PromptListResponse:
    """List all registered prompts with summary info."""
    if mlflow_registry is None:
        return PromptListResponse(prompts=[], total=0)
    try:
        names = mlflow_registry.list_prompts()
        summaries = []
        for name in names:
            info = mlflow_registry.get_prompt(name)
            if info:
                summaries.append(PromptSummary(
                    name=info.name,
                    version=info.version,
                    state=info.tags.get("state", "DRAFT"),
                    agent_code=info.tags.get("agent_code", ""),
                    workflow=info.tags.get("workflow", ""),
                ))
        return PromptListResponse(prompts=summaries, total=len(summaries))
    except Exception as exc:
        logger.error("Failed to list prompts: %s", exc)
        return PromptListResponse(prompts=[], total=0)


@router.get("/v1/prompts/{name}", response_model=PromptDetailResponse, response_model_exclude_none=True)
async def get_prompt_detail(name: str) -> PromptDetailResponse | JSONResponse:
    """Get full prompt detail with metadata (AC-2)."""
    if mlflow_registry is None:
        return JSONResponse(status_code=503, content={"detail": "Not initialized"})
    info = mlflow_registry.get_prompt(name)
    if info is None:
        return JSONResponse(status_code=404, content={"detail": f"Prompt '{name}' not found"})

    tags = info.tags
    metadata = PromptMetadata(
        workflow=tags.get("workflow", ""),
        agent_code=tags.get("agent_code", ""),
        agent_port=int(tags.get("agent_port", "0")),
        skill=tags.get("skill", ""),
        model_target=tags.get("model_target", "claude-sonnet-4-6"),
        optimization_group=tags.get("optimization_group", ""),
        tenant_overridable=tags.get("tenant_overridable", "true") == "true",
        optimization_priority=tags.get("optimization_priority", "MEDIUM"),
        last_optimized=tags.get("last_optimized") or None,
        optimization_run_id=tags.get("optimization_run_id") or None,
    )

    return PromptDetailResponse(
        name=info.name,
        version=info.version,
        template=info.template,
        state=tags.get("state", "DRAFT"),
        metadata=metadata,
        tags=tags,
    )


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


@router.put("/v1/prompts/{name}/versions/{version}/promote")
async def promote_prompt(
    name: str,
    version: int,
    request: PromptTransitionRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> PromptTransitionResponse:
    """Promote a prompt version to the next lifecycle state."""
    if lifecycle_manager is None:
        return PromptTransitionResponse(
            name=name, version=version, from_state="unknown",
            to_state=request.target_state, success=False,
            message="Lifecycle manager not initialized",
        )
    try:
        current = mlflow_registry.get_prompt(name) if mlflow_registry else None
        current_state = (current.tags.get("state", "DRAFT") if current else "DRAFT")

        from_state = PromptState(current_state)
        to_state = PromptState(request.target_state)

        if to_state == PromptState.PRODUCTION:
            lifecycle_manager.promote_to_production(
                name, version, tenant_id=request.tenant_id
            )
        else:
            lifecycle_manager.transition(
                name, version, from_state, to_state,
                tenant_id=request.tenant_id,
            )

        return PromptTransitionResponse(
            name=name, version=version, from_state=from_state.value,
            to_state=to_state.value, success=True,
        )
    except (InvalidTransitionError, ValueError) as exc:
        return PromptTransitionResponse(
            name=name, version=version, from_state="unknown",
            to_state=request.target_state, success=False, message=str(exc),
        )


@router.put("/v1/prompts/{name}/versions/{version}/reject")
async def reject_prompt(name: str, version: int) -> PromptTransitionResponse:
    """Reject a STAGING prompt version (AC-3: never hard-deleted)."""
    if lifecycle_manager is None:
        return PromptTransitionResponse(
            name=name, version=version, from_state="STAGING",
            to_state="REJECTED", success=False,
            message="Lifecycle manager not initialized",
        )
    try:
        lifecycle_manager.reject(name, version)
        return PromptTransitionResponse(
            name=name, version=version, from_state="STAGING",
            to_state="REJECTED", success=True,
        )
    except InvalidTransitionError as exc:
        return PromptTransitionResponse(
            name=name, version=version, from_state="STAGING",
            to_state="REJECTED", success=False, message=str(exc),
        )


@router.put("/v1/prompts/{name}/versions/{version}/rollback")
async def rollback_prompt(
    name: str,
    version: int,
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
) -> PromptTransitionResponse:
    """Roll back a CANARY or PRODUCTION version."""
    if lifecycle_manager is None:
        return PromptTransitionResponse(
            name=name, version=version, from_state="unknown",
            to_state="ROLLED_BACK", success=False,
            message="Lifecycle manager not initialized",
        )
    try:
        current = mlflow_registry.get_prompt(name) if mlflow_registry else None
        current_state = PromptState(
            current.tags.get("state", "PRODUCTION") if current else "PRODUCTION"
        )
        lifecycle_manager.rollback(name, version, current_state, tenant_id=x_tenant_id)
        return PromptTransitionResponse(
            name=name, version=version, from_state=current_state.value,
            to_state="ROLLED_BACK", success=True,
        )
    except InvalidTransitionError as exc:
        return PromptTransitionResponse(
            name=name, version=version, from_state="unknown",
            to_state="ROLLED_BACK", success=False, message=str(exc),
        )


@router.get("/v1/prompts/{name}/production", response_model=None)
async def get_production_prompt(
    name: str,
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
):
    """Get the current production version (AC-4, AC-5: tenant override first)."""
    if lifecycle_manager is None:
        return JSONResponse(status_code=503, content={"detail": "Not initialized"})
    prod = lifecycle_manager.get_production_version(name, tenant_id=x_tenant_id)
    if prod is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No production version found for '{name}'"},
        )
    return ProductionPromptResponse(
        name=prod.name,
        version=prod.version,
        template=prod.template,
        state=prod.tags.get("state", "PRODUCTION"),
        tenant_id=prod.tags.get("tenant_id"),
        tags=prod.tags,
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
