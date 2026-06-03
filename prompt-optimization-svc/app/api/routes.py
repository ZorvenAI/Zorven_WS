"""API routes for prompt-optimization-svc."""

import logging
from typing import Optional

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.api.schemas import (
    JointOptimizationResponse,
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
    SyntheticGenerateRequest,
    SyntheticGenerateResponse,
    ApprovalRequest,
    ApprovalResponse,
    RejectionRequest,
    TenantOverrideRequest,
    TenantOverrideResponse,
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


@router.get("/v1/prompts", response_model=None)
async def list_prompts():
    """List all registered prompts with summary info."""
    if mlflow_registry is None:
        return JSONResponse(
            status_code=503, content={"detail": "Registry not initialized"}
        )
    try:
        names = mlflow_registry.list_prompts()
        summaries = []
        for name in names:
            info = mlflow_registry.get_prompt(name)
            if info:
                summaries.append(
                    PromptSummary(
                        name=info.name,
                        version=info.version,
                        state=info.tags.get("state", "DRAFT"),
                        agent_code=info.tags.get("agent_code", ""),
                        workflow=info.tags.get("workflow", ""),
                    )
                )
        return PromptListResponse(prompts=summaries, total=len(summaries))
    except Exception as exc:
        logger.exception("Failed to list prompts: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": f"Registry error: {exc}"},
        )


@router.get("/v1/prompts/{name}", response_model=None)
async def get_prompt_detail(name: str):
    """Get full prompt detail with metadata (AC-2)."""
    if mlflow_registry is None:
        return JSONResponse(status_code=503, content={"detail": "Not initialized"})
    info = mlflow_registry.get_prompt(name)
    if info is None:
        return JSONResponse(
            status_code=404, content={"detail": f"Prompt '{name}' not found"}
        )

    tags = info.tags
    metadata = PromptMetadata(
        workflow=tags.get("workflow", ""),
        agent_code=tags.get("agent_code", ""),
        agent_port=int(tags.get("agent_port", "0")),
        skill=tags.get("skill", ""),
        model_target=tags.get("model_target", "claude-sonnet-4-6"),
        optimization_group=tags.get("optimization_group", ""),
        tenant_overridable=tags.get("tenant_overridable", "true").lower()
        in ("true", "1", "yes"),
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
        # AC-3: Validate placeholders against context variable registry
        agent_code = request.metadata.get("agent_code", "")
        warning_msg = ""
        if agent_code:
            from app.registries.context_variables import (
                validate_template_against_registry,
            )

            violations = validate_template_against_registry(
                request.template, agent_code
            )
            if violations:
                warning_msg = f"Registry warnings: {'; '.join(violations)}"
                logger.warning(
                    "Prompt %s has undeclared placeholders: %s",
                    request.name,
                    violations,
                )

        info = mlflow_registry.register_prompt(
            name=request.name,
            template=request.template,
            tags={**request.metadata, "state": "DRAFT"},
        )
        return PromptRegistrationResponse(
            name=info.name,
            version=info.version,
            status="registered",
            message=warning_msg,
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
            name=name,
            version=version,
            from_state="unknown",
            to_state=request.target_state,
            success=False,
            message="Lifecycle manager not initialized",
        )
    try:
        current = mlflow_registry.get_prompt(name) if mlflow_registry else None
        current_state = current.tags.get("state", "DRAFT") if current else "DRAFT"

        from_state = PromptState(current_state)
        to_state = PromptState(request.target_state)

        if to_state == PromptState.PRODUCTION:
            lifecycle_manager.promote_to_production(
                name, version, tenant_id=request.tenant_id
            )
        else:
            lifecycle_manager.transition(
                name,
                version,
                from_state,
                to_state,
                tenant_id=request.tenant_id,
            )

        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state=from_state.value,
            to_state=to_state.value,
            success=True,
        )
    except (InvalidTransitionError, ValueError) as exc:
        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state="unknown",
            to_state=request.target_state,
            success=False,
            message=str(exc),
        )


@router.put("/v1/prompts/{name}/versions/{version}/reject")
async def reject_prompt(name: str, version: int) -> PromptTransitionResponse:
    """Reject a STAGING prompt version (AC-3: never hard-deleted)."""
    if lifecycle_manager is None:
        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state="STAGING",
            to_state="REJECTED",
            success=False,
            message="Lifecycle manager not initialized",
        )
    try:
        lifecycle_manager.reject(name, version)
        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state="STAGING",
            to_state="REJECTED",
            success=True,
        )
    except InvalidTransitionError as exc:
        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state="STAGING",
            to_state="REJECTED",
            success=False,
            message=str(exc),
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
            name=name,
            version=version,
            from_state="unknown",
            to_state="ROLLED_BACK",
            success=False,
            message="Lifecycle manager not initialized",
        )
    try:
        current = mlflow_registry.get_prompt(name) if mlflow_registry else None
        current_state = PromptState(
            current.tags.get("state", "PRODUCTION") if current else "PRODUCTION"
        )
        lifecycle_manager.rollback(name, version, current_state, tenant_id=x_tenant_id)
        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state=current_state.value,
            to_state="ROLLED_BACK",
            success=True,
        )
    except InvalidTransitionError as exc:
        return PromptTransitionResponse(
            name=name,
            version=version,
            from_state="unknown",
            to_state="ROLLED_BACK",
            success=False,
            message=str(exc),
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


@router.post("/v1/optimize/group/{group_name}", response_model=None)
async def optimize_group(group_name: str):
    """Trigger joint optimization for a prompt group (US-019)."""
    from app.registries.optimization_groups import get_group

    try:
        group = get_group(group_name)
    except KeyError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    return JointOptimizationResponse(
        group_name=group_name,
        prompt_count=len(group.prompt_names),
    )


@router.get("/v1/optimize/runs", response_model=None)
async def list_optimization_runs():
    """AC-4: List active optimization runs from Redis progress hashes."""
    from app.api.schemas import RunListResponse, RunStatusResponse
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        runs = []
        r = await cache.connect()
        async for key in r.scan_iter(match="prompt:optimization:progress:*"):
            run_id = key.split(":")[-1]
            progress = await cache.get_optimization_progress(run_id)
            if progress:
                runs.append(
                    RunStatusResponse(
                        run_id=run_id,
                        state=progress.get("state", "UNKNOWN"),
                        prompt_name=progress.get("prompt_name", ""),
                        agent_code=progress.get("agent_code", ""),
                        updated_at=progress.get("updated_at"),
                    )
                )
        return RunListResponse(runs=runs, total=len(runs))
    finally:
        await cache.close()


@router.get("/v1/optimize/runs/{run_id}", response_model=None)
async def get_optimization_run(run_id: str):
    """Get optimization run detail from Redis progress hash."""
    from app.api.schemas import RunStatusResponse
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        progress = await cache.get_optimization_progress(run_id)
        if progress is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "Run not found"},
            )
        return RunStatusResponse(
            run_id=run_id,
            state=progress.get("state", "UNKNOWN"),
            prompt_name=progress.get("prompt_name", ""),
            agent_code=progress.get("agent_code", ""),
            error_message=progress.get("error_message", ""),
            deferred_until=progress.get("deferred_until"),
            updated_at=progress.get("updated_at"),
        )
    finally:
        await cache.close()


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


@router.post("/v1/datasets/seed", response_model=None)
async def seed_golden_datasets():
    """Seed golden evaluation datasets into PostgreSQL."""
    from app.api.schemas import DatasetSeedResponse
    from app.datasets.seeder import seed_golden_datasets as do_seed
    from app.models.database import async_session_factory

    result = await do_seed(async_session_factory)
    return DatasetSeedResponse(
        created=result.created,
        skipped=result.skipped,
        errors=result.errors,
        details=result.details,
    )


@router.get("/v1/datasets/stats", response_model=None)
async def get_dataset_stats():
    """Get golden dataset statistics per agent and source."""
    from collections import Counter

    from app.api.schemas import DatasetStatsResponse
    from app.datasets.golden_seed import GOLDEN_EXAMPLES

    agent_counts = Counter(e.agent_code for e in GOLDEN_EXAMPLES)
    source_counts = Counter(e.source for e in GOLDEN_EXAMPLES)
    industries = {
        e.metadata_extra.get("industry", "")
        for e in GOLDEN_EXAMPLES
        if e.metadata_extra.get("industry")
    }

    return DatasetStatsResponse(
        per_agent=dict(agent_counts),
        per_source=dict(source_counts),
        industry_count=len(industries),
        total=len(GOLDEN_EXAMPLES),
    )


@router.post("/v1/datasets/generate", response_model=SyntheticGenerateResponse)
async def generate_synthetic_datasets(request: SyntheticGenerateRequest):
    """Generate synthetic brand profiles using Claude Sonnet 4."""
    import anyio

    from app.core.config import settings
    from app.datasets.synthetic_context_gen import SyntheticContextGenerator

    if not settings.ANTHROPIC_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"detail": "Anthropic API key not configured"},
        )

    generator = SyntheticContextGenerator(api_key=settings.ANTHROPIC_API_KEY)
    tuples = [
        (request.industry, request.brand_maturity, request.objective)
    ] * request.count

    # Offload blocking Anthropic calls to threadpool
    examples, errors = await anyio.to_thread.run_sync(
        lambda: generator.generate_batch(
            tuples=tuples,
            prompt_name=request.prompt_name,
            agent_code=request.agent_code,
        )
    )

    return SyntheticGenerateResponse(
        examples=[
            {
                "prompt_name": e.prompt_name,
                "agent_code": e.agent_code,
                "input_context": e.input_context,
                "expected_output": e.expected_output,
                "source": e.source,
                "metadata_extra": e.metadata_extra,
            }
            for e in examples
        ],
        total=len(examples),
    )


@router.get("/v1/config/dataset-size", response_model=None)
async def get_dataset_size(
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
):
    """Get the golden dataset size limit for a tenant."""
    from app.api.schemas import DatasetSizeConfigResponse
    from app.cache.prompt_cache import PromptCacheManager
    from app.cache.tenant_config import (
        MAX_DATASET_SIZE,
        MIN_DATASET_SIZE,
        TenantConfigManager,
    )
    from app.core.config import settings

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        mgr = TenantConfigManager(cache)
        size = await mgr.get_golden_dataset_size(x_tenant_id)
        return DatasetSizeConfigResponse(
            tenant_id=x_tenant_id or "default",
            size=size,
            min_size=MIN_DATASET_SIZE,
            max_size=MAX_DATASET_SIZE,
        )
    finally:
        await cache.close()


@router.put("/v1/config/dataset-size", response_model=None)
async def set_dataset_size(
    request: "DatasetSizeConfigRequest",
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
):
    """Set the golden dataset size limit for a tenant (AC-3: validates [3, 50])."""
    from app.api.schemas import (
        DatasetSizeConfigRequest,
        DatasetSizeConfigResponse,
    )
    from app.cache.prompt_cache import PromptCacheManager
    from app.cache.tenant_config import (
        MAX_DATASET_SIZE,
        MIN_DATASET_SIZE,
        TenantConfigManager,
    )
    from app.core.config import settings

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        mgr = TenantConfigManager(cache)
        await mgr.set_golden_dataset_size(x_tenant_id, request.size)
        size = await mgr.get_golden_dataset_size(x_tenant_id)
        return DatasetSizeConfigResponse(
            tenant_id=x_tenant_id,
            size=size,
            min_size=MIN_DATASET_SIZE,
            max_size=MAX_DATASET_SIZE,
        )
    finally:
        await cache.close()


@router.post("/v1/optimize/runs/{run_id}/approve", response_model=ApprovalResponse)
async def approve_optimization_run(run_id: str, request: ApprovalRequest):
    """Approve a PENDING_APPROVAL optimization run for canary (AC-3)."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings
    from app.logic.approval_gate import approve_run
    from app.logic.run_lifecycle import InvalidRunTransitionError, RunLifecycleManager
    from app.models.database import async_session_factory

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        # Validate run exists and is PENDING_APPROVAL
        progress = await cache.get_optimization_progress(run_id)
        if progress is None:
            return JSONResponse(status_code=404, content={"detail": "Run not found"})
        if progress.get("state") != "PENDING_APPROVAL":
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f"Run is in state '{progress.get('state')}', "
                    f"not PENDING_APPROVAL"
                },
            )

        mgr = RunLifecycleManager(
            prompt_cache=cache, db_session_factory=async_session_factory
        )
        try:
            decision = await approve_run(
                run_id=run_id,
                approved_by=request.approved_by,
                lifecycle_manager=mgr,
                prompt_name=progress.get("prompt_name", ""),
                agent_code=progress.get("agent_code", ""),
            )
        except InvalidRunTransitionError as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})

        return ApprovalResponse(
            run_id=decision.run_id,
            decision=decision.decision,
            approved_by=decision.approved_by,
            decided_at=decision.decided_at.isoformat(),
        )
    finally:
        await cache.close()


@router.post("/v1/optimize/runs/{run_id}/reject", response_model=ApprovalResponse)
async def reject_optimization_run(run_id: str, request: RejectionRequest):
    """Reject a PENDING_APPROVAL optimization run (AC-3)."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings
    from app.logic.approval_gate import reject_run
    from app.logic.run_lifecycle import InvalidRunTransitionError, RunLifecycleManager
    from app.models.database import async_session_factory

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        progress = await cache.get_optimization_progress(run_id)
        if progress is None:
            return JSONResponse(status_code=404, content={"detail": "Run not found"})
        if progress.get("state") != "PENDING_APPROVAL":
            return JSONResponse(
                status_code=409,
                content={
                    "detail": f"Run is in state '{progress.get('state')}', "
                    f"not PENDING_APPROVAL"
                },
            )

        mgr = RunLifecycleManager(
            prompt_cache=cache, db_session_factory=async_session_factory
        )
        try:
            decision = await reject_run(
                run_id=run_id,
                approved_by=request.approved_by,
                reason=request.reason,
                lifecycle_manager=mgr,
                prompt_name=progress.get("prompt_name", ""),
                agent_code=progress.get("agent_code", ""),
            )
        except InvalidRunTransitionError as exc:
            return JSONResponse(status_code=409, content={"detail": str(exc)})

        return ApprovalResponse(
            run_id=decision.run_id,
            decision=decision.decision,
            approved_by=decision.approved_by,
            decided_at=decision.decided_at.isoformat(),
        )
    finally:
        await cache.close()


@router.post(
    "/v1/prompts/{name}/tenant-overrides",
    response_model=TenantOverrideResponse,
)
async def create_tenant_override_endpoint(
    name: str,
    request: TenantOverrideRequest,
    x_tenant_id: str = Header(default="", alias="X-Tenant-ID"),
):
    """Create a tenant-specific prompt override (AC-1: OWNER only)."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings
    from app.logic.tenant_override import create_tenant_override

    # Verify tenant_id matches the authenticated tenant
    if x_tenant_id and request.tenant_id != x_tenant_id:
        return JSONResponse(
            status_code=403,
            content={"detail": "tenant_id in body must match X-Tenant-ID header"},
        )

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        result = await create_tenant_override(
            prompt_name=name,
            tenant_id=request.tenant_id,
            template=request.template,
            mlflow_registry=mlflow_registry,
            prompt_cache=cache,
        )
        return TenantOverrideResponse(**result)
    finally:
        await cache.close()


@router.get(
    "/v1/prompts/{name}/tenant-overrides/{tenant_id}",
    response_model=TenantOverrideResponse,
)
async def get_tenant_override_endpoint(name: str, tenant_id: str):
    """Get a tenant-specific prompt override."""
    from app.logic.tenant_override import get_tenant_override

    result = await get_tenant_override(
        prompt_name=name,
        tenant_id=tenant_id,
        mlflow_registry=mlflow_registry,
    )
    if result is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No tenant override for '{name}' tenant '{tenant_id}'"},
        )
    return TenantOverrideResponse(**result)


@router.delete(
    "/v1/prompts/{name}/tenant-overrides/{tenant_id}",
)
async def delete_tenant_override_endpoint(name: str, tenant_id: str):
    """Delete a tenant-specific prompt override (AC-1, AC-3)."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings
    from app.logic.tenant_override import delete_tenant_override

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        deleted = await delete_tenant_override(
            prompt_name=name,
            tenant_id=tenant_id,
            mlflow_registry=mlflow_registry,
            prompt_cache=cache,
        )
        if not deleted:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"No tenant override for '{name}' tenant '{tenant_id}'"
                },
            )
        return JSONResponse(
            status_code=200,
            content={
                "detail": f"Tenant override deleted for '{name}' tenant '{tenant_id}'"
            },
        )
    finally:
        await cache.close()


@router.get("/v1/config/tenant/{tenant_id}", response_model=None)
async def get_tenant_config(
    tenant_id: str,
    x_tenant_id: str = Header(default="", alias="X-Tenant-ID"),
):
    """Get all tenant optimization configuration keys (AC-2: defaults applied)."""
    from app.api.schemas import TenantOptimizationConfig
    from app.cache.prompt_cache import PromptCacheManager
    from app.cache.tenant_config import TenantConfigManager
    from app.core.config import settings

    if x_tenant_id and tenant_id != x_tenant_id:
        return JSONResponse(
            status_code=403,
            content={"detail": "Cannot read another tenant's configuration"},
        )

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        mgr = TenantConfigManager(cache)
        return TenantOptimizationConfig(
            tenant_id=tenant_id,
            prompt_optimization_enabled=await mgr.get_optimization_enabled(tenant_id),
            prompt_auto_promotion=await mgr.get_auto_promotion(tenant_id),
            prompt_optimization_model=await mgr.get_optimization_model(tenant_id),
            prompt_optimization_budget=await mgr.get_optimization_budget(tenant_id),
            prompt_promotion_threshold=await mgr.get_promotion_threshold(tenant_id),
            prompt_cache_ttl_seconds=await mgr.get_prompt_cache_ttl(tenant_id),
            golden_dataset_default_size=await mgr.get_golden_dataset_size(tenant_id),
            wf3_optimization_schedule=await mgr.get_optimization_schedule(tenant_id),
        )
    finally:
        await cache.close()


@router.put("/v1/config/tenant/{tenant_id}", response_model=None)
async def update_tenant_config(
    tenant_id: str,
    request: "TenantConfigUpdateRequest",
    x_tenant_id: str = Header(default="", alias="X-Tenant-ID"),
):
    """Update tenant optimization configuration keys."""
    from app.api.schemas import TenantConfigUpdateRequest, TenantOptimizationConfig

    if x_tenant_id and tenant_id != x_tenant_id:
        return JSONResponse(
            status_code=403,
            content={"detail": "Cannot modify another tenant's configuration"},
        )
    from app.cache.prompt_cache import PromptCacheManager
    from app.cache.tenant_config import TenantConfigManager
    from app.core.config import settings

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        mgr = TenantConfigManager(cache)
        if request.prompt_optimization_enabled is not None:
            await mgr.set_optimization_enabled(
                tenant_id, request.prompt_optimization_enabled
            )
        if request.prompt_auto_promotion is not None:
            await mgr.set_auto_promotion(tenant_id, request.prompt_auto_promotion)
        if request.prompt_optimization_model is not None:
            await mgr.set_optimization_model(
                tenant_id, request.prompt_optimization_model
            )
        if request.prompt_optimization_budget is not None:
            await mgr.set_optimization_budget(
                tenant_id, request.prompt_optimization_budget
            )
        if request.prompt_promotion_threshold is not None:
            await mgr.set_promotion_threshold(
                tenant_id, request.prompt_promotion_threshold
            )
        if request.prompt_cache_ttl_seconds is not None:
            await mgr.set_prompt_cache_ttl(tenant_id, request.prompt_cache_ttl_seconds)
        if request.golden_dataset_default_size is not None:
            await mgr.set_golden_dataset_size(
                tenant_id, request.golden_dataset_default_size
            )
        if request.wf3_optimization_schedule is not None:
            await mgr.set_optimization_schedule(
                tenant_id, request.wf3_optimization_schedule
            )

        # Return updated config
        return TenantOptimizationConfig(
            tenant_id=tenant_id,
            prompt_optimization_enabled=await mgr.get_optimization_enabled(tenant_id),
            prompt_auto_promotion=await mgr.get_auto_promotion(tenant_id),
            prompt_optimization_model=await mgr.get_optimization_model(tenant_id),
            prompt_optimization_budget=await mgr.get_optimization_budget(tenant_id),
            prompt_promotion_threshold=await mgr.get_promotion_threshold(tenant_id),
            prompt_cache_ttl_seconds=await mgr.get_prompt_cache_ttl(tenant_id),
            golden_dataset_default_size=await mgr.get_golden_dataset_size(tenant_id),
            wf3_optimization_schedule=await mgr.get_optimization_schedule(tenant_id),
        )
    finally:
        await cache.close()
