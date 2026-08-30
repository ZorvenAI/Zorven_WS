"""API routes for prompt-optimization-svc."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from fastapi import Query

from app.api.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ExecuteRequest,
    ExecuteResponse,
    GoldenDatasetCreateRequest,
    GoldenDatasetListResponse,
    GoldenDatasetResponse,
    GoldenDatasetUpdateRequest,
    HealthResponse,
    JointOptimizationResponse,
    MiningTriggerResponse,
    PlatformOptimizationResponse,
    ProductionPromptResponse,
    PromptDetailResponse,
    PromptListResponse,
    PromptMetadata,
    PromptRegistrationRequest,
    PromptRegistrationResponse,
    PromptSummary,
    PromptTransitionRequest,
    PromptTransitionResponse,
    RejectionRequest,
    SeedResponse,
    SingleAgentOptimizationResponse,
    SyntheticGenerateRequest,
    SyntheticGenerateResponse,
    TenantOverrideRequest,
    TenantOverrideResponse,
)
from app.api.schemas import (
    DatasetSizeConfigRequest,
)  # noqa: E402 — top-level for FastAPI
from app.api.schemas import (
    TenantConfigUpdateRequest,
)  # noqa: E402 — top-level for FastAPI
from app.auth.rbac import Decision, Permission, Role, require_permission, resolve_role
from app.logic.lifecycle import (
    InvalidTransitionError,
    PromptLifecycleManager,
    PromptState,
)
from app.services.health_checker import HealthChecker
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


def _float_or_none(value) -> Optional[float]:
    """Safely convert a Redis hash value to float or None."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# Module-level dependencies — initialized in main.py lifespan
health_checker: Optional[HealthChecker] = None
mlflow_registry: Optional[MLflowPromptRegistry] = None
lifecycle_manager: Optional[PromptLifecycleManager] = None
canary_manager = None  # Optional[CanaryManager] — set in main.py lifespan


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check with dependency status."""
    if health_checker is not None:
        return await health_checker.check_all()
    return HealthResponse(status="unhealthy", dependencies=[])


@router.get("/v1/prompts", response_model=None)
async def list_prompts(
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
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
async def get_prompt_detail(
    name: str,
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
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


@router.get("/v1/prompts/{name}/versions/{version}", response_model=None)
async def get_prompt_version(
    name: str,
    version: int,
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
    """Get specific prompt version with template and metadata (§13.1)."""
    if mlflow_registry is None:
        return JSONResponse(status_code=503, content={"detail": "Not initialized"})
    info = mlflow_registry.get_prompt_version(name, version)
    if info is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Prompt '{name}' version {version} not found"},
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
    decision: Decision = Depends(require_permission(Permission.REGISTER)),
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


@router.post("/v1/prompts/seed-to-production", response_model=SeedResponse)
async def seed_to_production_endpoint(
    decision: Decision = Depends(require_permission(Permission.PROMOTE)),
) -> SeedResponse:
    """Seed all catalog prompts and promote them to PRODUCTION.

    Walks each prompt through the full lifecycle sequence
    (DRAFT → STAGING → CANARY → PRODUCTION). Idempotent — prompts already
    at PRODUCTION are skipped. Resumes from intermediate states.
    """
    if mlflow_registry is None or lifecycle_manager is None:
        return SeedResponse(
            errors=1,
            details=["MLflow or lifecycle manager not initialized"],
        )
    from app.services.prompt_seeder import seed_to_production

    result = seed_to_production(mlflow_registry, lifecycle_manager)
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
    decision: Decision = Depends(require_permission(Permission.PROMOTE)),
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
    decision: Decision = Depends(require_permission(Permission.ROLLBACK)),
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
    """Get the current production version with canary-aware routing.

    If an active canary exists and the tenant is in the 10% canary bucket,
    returns the canary version instead of the production version.
    """
    if lifecycle_manager is None:
        return JSONResponse(status_code=503, content={"detail": "Not initialized"})

    # Check for active canary routing
    # Wrapped in try/except: canary check must never break the production hot path
    if canary_manager and x_tenant_id:
        try:
            from app.logic.canary_manager import is_canary_request

            canary_state = await canary_manager.get_canary_state(name)
            if canary_state and canary_state.active:
                if is_canary_request(x_tenant_id):
                    # Route to canary version
                    if mlflow_registry:
                        canary_prompt = mlflow_registry.get_prompt_version(
                            name, canary_state.canary_version
                        )
                        if canary_prompt:
                            return ProductionPromptResponse(
                                name=name,
                                version=canary_prompt.version,
                                template=canary_prompt.template,
                                state="CANARY",
                                tags={**canary_prompt.tags, "is_canary": "true"},
                            )
        except Exception as exc:
            logger.warning("Canary check failed (falling through): %s", exc)

    # Normal production resolution
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
async def optimize_group(
    group_name: str,
    decision: Decision = Depends(require_permission(Permission.TRIGGER_OPTIMIZATION)),
):
    """Trigger joint optimization for a prompt group (§13.2)."""
    from app.registries.optimization_groups import get_group

    try:
        group = get_group(group_name)
    except KeyError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    return JointOptimizationResponse(
        group_name=group_name,
        prompt_count=len(group.prompt_names),
    )


@router.post("/v1/optimize/agent/{agent_code}", response_model=None)
async def optimize_agent(
    agent_code: str,
    decision: Decision = Depends(require_permission(Permission.TRIGGER_OPTIMIZATION)),
):
    """Trigger optimization for all prompts of a single agent (§13.2)."""
    from app.registries.prompt_catalog import AGENT_PORTS, PROMPT_CATALOG

    if agent_code not in AGENT_PORTS:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown agent_code: '{agent_code}'"},
        )

    # Find all prompts for this agent
    agent_prompts = [
        entry.name
        for entry in PROMPT_CATALOG
        if entry.tags.get("agent_code") == agent_code
    ]

    return SingleAgentOptimizationResponse(
        agent_code=agent_code,
        prompt_count=len(agent_prompts),
        state="QUEUED",
        message=f"Optimization queued for {len(agent_prompts)} prompt(s)",
    )


@router.post("/v1/optimize/all", response_model=None)
async def optimize_all(
    x_user_role: str = Header(default="", alias="X-User-Role"),
):
    """AC-1: Trigger platform-wide optimization — OWNER only."""
    from app.registries.optimization_groups import OPTIMIZATION_GROUPS
    from app.registries.prompt_catalog import PROMPT_CATALOG

    # OWNER-only enforcement (AC-1)
    role = resolve_role(x_user_role)
    if role != Role.OWNER:
        return JSONResponse(
            status_code=403,
            content={"detail": "Platform-wide optimization requires OWNER role"},
        )

    total_prompts = len(PROMPT_CATALOG)
    group_names = list(OPTIMIZATION_GROUPS.keys())

    return PlatformOptimizationResponse(
        groups_triggered=len(group_names),
        total_prompts=total_prompts,
        runs=group_names,
        message=f"Platform-wide optimization queued: {len(group_names)} groups, "
        f"{total_prompts} prompts",
    )


@router.get("/v1/optimize/runs", response_model=None)
async def list_optimization_runs(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Page size"),
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
    """AC-2: List optimization runs with status, metrics, and cost (paginated).

    Reads from PostgreSQL (durable). Falls back to Redis if PostgreSQL
    has no data yet (pre-migration runs).
    """
    from app.api.schemas import RunListResponse, RunStatusResponse

    # Try PostgreSQL first
    try:
        from sqlalchemy import func, select

        from app.models.database import async_session_factory
        from app.models.optimization_run import OptimizationRun

        async with async_session_factory() as session:
            count_stmt = select(func.count()).select_from(OptimizationRun)
            total = (await session.execute(count_stmt)).scalar() or 0

            if total > 0:
                offset = (page - 1) * page_size
                stmt = (
                    select(OptimizationRun)
                    .order_by(OptimizationRun.updated_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                runs = [
                    RunStatusResponse(
                        run_id=row.id,
                        state=row.state,
                        prompt_name=row.prompt_name,
                        agent_code=row.agent_code,
                        error_message=row.error_message or "",
                        updated_at=(
                            row.updated_at.isoformat() if row.updated_at else None
                        ),
                        score_before=row.score_before,
                        score_after=row.score_after,
                        improvement=row.improvement,
                        cost_usd=row.cost_usd,
                    )
                    for row in rows
                ]
                return RunListResponse(
                    runs=runs, total=total, page=page, page_size=page_size
                )
    except Exception:
        pass  # Fall through to Redis

    # Fallback: read from Redis (pre-migration data)
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    r = await cache.connect()
    try:
        all_runs = []
        async for key in r.scan_iter(match="prompt:optimization:progress:*"):
            run_id = key.split(":")[-1]
            progress = await cache.get_optimization_progress(run_id)
            if progress:
                all_runs.append(
                    RunStatusResponse(
                        run_id=run_id,
                        state=progress.get("state", "UNKNOWN"),
                        prompt_name=progress.get("prompt_name", ""),
                        agent_code=progress.get("agent_code", ""),
                        updated_at=progress.get("updated_at"),
                        score_before=_float_or_none(progress.get("score_before")),
                        score_after=_float_or_none(progress.get("score_after")),
                        improvement=_float_or_none(progress.get("improvement")),
                        cost_usd=_float_or_none(progress.get("cost_usd")),
                    )
                )
        total = len(all_runs)
        start = (page - 1) * page_size
        end = start + page_size
        return RunListResponse(
            runs=all_runs[start:end],
            total=total,
            page=page,
            page_size=page_size,
        )
    finally:
        await cache.close()


@router.get("/v1/optimize/runs/{run_id}", response_model=None)
async def get_optimization_run(
    run_id: str,
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
    """AC-3: Get optimization run detail with GEPA traces and reflection prompts."""
    import json

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

        # AC-3: Parse GEPA traces and reflection prompts from Redis
        raw_traces = progress.get("gepa_traces", "[]")
        if isinstance(raw_traces, str):
            try:
                gepa_traces = json.loads(raw_traces)
            except (json.JSONDecodeError, TypeError):
                gepa_traces = []
        else:
            gepa_traces = raw_traces if isinstance(raw_traces, list) else []

        raw_reflections = progress.get("reflection_prompts", "[]")
        if isinstance(raw_reflections, str):
            try:
                reflection_prompts = json.loads(raw_reflections)
            except (json.JSONDecodeError, TypeError):
                reflection_prompts = []
        else:
            reflection_prompts = (
                raw_reflections if isinstance(raw_reflections, list) else []
            )

        return RunStatusResponse(
            run_id=run_id,
            state=progress.get("state", "UNKNOWN"),
            prompt_name=progress.get("prompt_name", ""),
            agent_code=progress.get("agent_code", ""),
            error_message=progress.get("error_message", ""),
            deferred_until=progress.get("deferred_until"),
            updated_at=progress.get("updated_at"),
            score_before=_float_or_none(progress.get("score_before")),
            score_after=_float_or_none(progress.get("score_after")),
            improvement=_float_or_none(progress.get("improvement")),
            cost_usd=_float_or_none(progress.get("cost_usd")),
            gepa_traces=gepa_traces,
            reflection_prompts=reflection_prompts,
        )
    finally:
        await cache.close()


@router.post("/v1/execute", response_model=None)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
):
    """Execute on-demand single-prompt GEPA optimization."""
    config = request.config or {}
    prompt_name = config.get("prompt_name")
    agent_code = config.get("agent_code", "unknown")
    if not prompt_name:
        return JSONResponse(
            status_code=400,
            content={"detail": "config.prompt_name is required"},
        )

    from app.predict_fns.factory import make_predict_fn
    from app.scorers import COMMON_SCORERS
    from app.services.gepa_optimizer import ZorvenGepaOptimizer

    # Resolve latest version — MLflow requires version in prompt URI
    prompt_version = None
    if mlflow_registry:
        prompt_info = mlflow_registry.get_prompt(prompt_name)
        if prompt_info:
            prompt_version = prompt_info.version
    if not prompt_version:
        prompt_version = 1

    predict_fn = make_predict_fn(prompt_name)
    gepa = ZorvenGepaOptimizer()
    result = gepa.optimize(
        prompt_uris=[f"prompts:/{prompt_name}/{prompt_version}"],
        predict_fn=predict_fn,
        train_data=[{"inputs": request.input_context or {}}],
        scorers=COMMON_SCORERS,
        agent_code=agent_code,
        tenant_id=x_tenant_id if x_tenant_id != "default" else None,
    )
    return {
        "status": "completed" if not result.error else "failed",
        "best_prompt": result.best_prompt,
        "best_score": result.best_score,
        "candidates_evaluated": result.candidates_evaluated,
        "mlflow_run_id": result.mlflow_run_id,
        "duration_seconds": result.duration_seconds,
        "error": result.error,
    }


@router.post("/v1/optimize", response_model=None, status_code=202)
async def optimize(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.PROMOTE)),
):
    """Trigger GEPA group optimization via Celery task."""
    config = request.config or {}
    group_name = config.get("group_name")
    if not group_name:
        return JSONResponse(
            status_code=400,
            content={"detail": "config.group_name is required"},
        )

    from app.registries.optimization_groups import get_group

    try:
        group = get_group(group_name)
    except KeyError as exc:
        return JSONResponse(
            status_code=400,
            content={"detail": str(exc)},
        )

    # Route to the correct Celery task based on workflow
    task_map = {
        0: "app.tasks.optimize_oia_pipeline.optimize_oia_pipeline",
        1: "app.tasks.optimize_wf1_pipeline.optimize_wf1_pipeline",
        2: "app.tasks.optimize_wf2_pipeline.optimize_wf2_pipeline",
    }
    if group.workflow == 3:
        if "coa" in group.agent_codes or "ila" in group.agent_codes:
            task_name = "app.tasks.optimize_wf3_pipeline.optimize_wf3_optimization_loop"
        else:
            task_name = "app.tasks.optimize_wf3_pipeline.optimize_wf3_creative_pipeline"
    else:
        task_name = task_map.get(group.workflow)

    if not task_name:
        return JSONResponse(
            status_code=400,
            content={"detail": f"No task mapped for workflow {group.workflow}"},
        )

    from app.celery_app import celery_app

    # All tasks accept force=True to bypass schedule guards for on-demand triggers
    result = celery_app.send_task(task_name, kwargs={"force": True})

    return JSONResponse(
        status_code=202,
        content={
            "status": "QUEUED",
            "task_id": result.id,
            "group_name": group_name,
            "prompt_count": len(group.prompt_names),
            "agent_codes": list(group.agent_codes),
        },
    )


@router.get("/v1/optimize/locks", response_model=None)
async def list_optimization_locks(
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
    """List all active optimization locks with TTL info."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings

    cache = PromptCacheManager(settings.PROMPT_CACHE_REDIS_URL)
    redis = await cache.connect()
    try:
        keys = []
        async for key in redis.scan_iter("prompt:optimization:lock:*"):
            ttl = await redis.ttl(key)
            owner = await redis.get(key)
            group = key.replace("prompt:optimization:lock:", "")
            keys.append({"group": group, "owner": owner, "ttl_seconds": ttl})
        return {"locks": keys}
    finally:
        await cache.close()


@router.delete("/v1/optimize/locks/{group_name}", response_model=None)
async def clear_optimization_lock(
    group_name: str,
    decision: Decision = Depends(require_permission(Permission.PROMOTE)),
):
    """Clear a stale optimization lock for a group (admin only)."""
    from app.cache.prompt_cache import PromptCacheManager
    from app.core.config import settings

    cache = PromptCacheManager(settings.PROMPT_CACHE_REDIS_URL)
    redis = await cache.connect()
    try:
        key = f"prompt:optimization:lock:{group_name}"
        deleted = await redis.delete(key)
        if deleted:
            logger.info("Admin cleared optimization lock: group=%s", group_name)
            return {"status": "cleared", "group": group_name}
        return JSONResponse(
            status_code=404,
            content={"detail": f"No lock found for group '{group_name}'"},
        )
    finally:
        await cache.close()


@router.get("/v1/config", response_model=None)
async def get_service_config(
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
    """Return current configurable settings (for debugging/testing)."""
    from app.core.config import settings

    return {
        "optimization": {
            "gepa_model_name": settings.GEPA_MODEL_NAME,
            "gepa_max_tokens": settings.GEPA_MAX_TOKENS,
            "gepa_reflection_model": settings.GEPA_REFLECTION_MODEL,
            "default_optimization_budget": settings.DEFAULT_OPTIMIZATION_BUDGET,
            "cost_per_candidate_usd": settings.COST_PER_CANDIDATE_USD,
            "optimization_cost_cap_usd": settings.OPTIMIZATION_COST_CAP_USD,
        },
        "locks": {
            "lock_ttl_seconds": settings.OPTIMIZATION_LOCK_TTL,
            "deferred_retry_seconds": settings.DEFERRED_RETRY_SECONDS,
        },
        "canary": {
            "traffic_pct": settings.CANARY_TRAFFIC_PCT,
            "duration_hours": settings.CANARY_DURATION_HOURS,
            "regression_threshold": settings.CANARY_REGRESSION_THRESHOLD,
        },
        "validation": {
            "holdout_pct": settings.VALIDATION_HOLDOUT_PCT,
            "improvement_threshold": settings.VALIDATION_IMPROVEMENT_THRESHOLD,
            "regression_threshold": settings.VALIDATION_REGRESSION_THRESHOLD,
            "length_multiplier_limit": settings.LENGTH_MULTIPLIER_LIMIT,
        },
        "circuit_breaker": {
            "failure_threshold_seconds": settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD_SECONDS,
            "half_open_interval_seconds": settings.CIRCUIT_BREAKER_HALF_OPEN_INTERVAL_SECONDS,
        },
        "auto_rollback": {
            "regression_threshold": settings.AUTO_ROLLBACK_REGRESSION_THRESHOLD,
            "window_hours": settings.AUTO_ROLLBACK_WINDOW_HOURS,
        },
        "approval": {
            "critical_agents": settings.CRITICAL_AGENTS,
        },
        "cache": {
            "prompt_cache_ttl": settings.PROMPT_CACHE_TTL,
            "progress_ttl": settings.OPTIMIZATION_PROGRESS_TTL,
        },
    }


@router.post("/v1/datasets/seed", response_model=None)
async def seed_golden_datasets(
    decision: Decision = Depends(require_permission(Permission.REGISTER)),
):
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
async def get_dataset_stats(
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
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
async def generate_synthetic_datasets(
    request: SyntheticGenerateRequest,
    decision: Decision = Depends(require_permission(Permission.REGISTER)),
):
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


# ── §13.3 Dataset CRUD + Mine endpoints ──


VALID_SOURCES = {"manual", "synthetic", "mined", "adversarial"}


@router.get("/v1/datasets/{agent_code}", response_model=GoldenDatasetListResponse)
async def list_datasets(
    agent_code: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Page size"),
    source: Optional[str] = Query(default=None, description="Filter by source"),
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.VIEW)),
):
    """AC-3: List golden dataset entries for an agent with pagination and filtering."""
    from sqlalchemy import func, select

    from app.models.database import async_session_factory
    from app.models.golden_dataset import GoldenDataset
    from app.registries.prompt_catalog import AGENT_PORTS

    if agent_code not in AGENT_PORTS:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown agent_code: '{agent_code}'"},
        )

    if source is not None and source not in VALID_SOURCES:
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"Invalid source '{source}'. "
                f"Valid values: {', '.join(sorted(VALID_SOURCES))}"
            },
        )

    async with async_session_factory() as session:
        base_filter = [
            GoldenDataset.agent_code == agent_code,
            GoldenDataset.active.is_(True),
        ]
        # Tenant isolation: show global rows + tenant-scoped rows
        if x_tenant_id:
            base_filter.append(GoldenDataset.tenant_id.in_([x_tenant_id, None]))
        if source is not None:
            base_filter.append(GoldenDataset.source == source)

        # Total count
        count_stmt = select(func.count(GoldenDataset.id)).where(*base_filter)
        total = (await session.execute(count_stmt)).scalar() or 0

        # Paginated results
        stmt = (
            select(GoldenDataset)
            .where(*base_filter)
            .order_by(GoldenDataset.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await session.execute(stmt)).scalars().all()

        items = [
            GoldenDatasetResponse(
                id=row.id,
                prompt_name=row.prompt_name,
                agent_code=row.agent_code,
                source=row.source,
                metadata_extra=row.metadata_extra or {},
                active=row.active,
                tenant_id=row.tenant_id,
                input_context=row.input_context or {},
                expected_output=row.expected_output,
                quality_score=row.quality_score,
                created_at=row.created_at.isoformat() if row.created_at else None,
                updated_at=row.updated_at.isoformat() if row.updated_at else None,
            )
            for row in rows
        ]

    return GoldenDatasetListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.post(
    "/v1/datasets/{agent_code}",
    response_model=GoldenDatasetResponse,
    status_code=201,
)
async def create_dataset_entry(
    agent_code: str,
    request: GoldenDatasetCreateRequest,
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.REGISTER)),
):
    """Create a golden dataset entry for an agent."""
    from app.models.database import async_session_factory
    from app.models.golden_dataset import GoldenDataset
    from app.registries.prompt_catalog import AGENT_PORTS

    if agent_code not in AGENT_PORTS:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown agent_code: '{agent_code}'"},
        )

    # Tenant isolation: body tenant_id must match header if both provided
    effective_tenant = request.tenant_id or x_tenant_id
    if x_tenant_id and request.tenant_id and request.tenant_id != x_tenant_id:
        return JSONResponse(
            status_code=403,
            content={"detail": "tenant_id in body must match X-Tenant-ID header"},
        )

    async with async_session_factory() as session:
        entry = GoldenDataset(
            prompt_name=request.prompt_name,
            agent_code=agent_code,
            tenant_id=effective_tenant,
            input_context=request.input_context,
            expected_output=request.expected_output,
            source=request.source,
            quality_score=request.quality_score,
            active=True,
            metadata_extra=request.metadata_extra,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)

        return GoldenDatasetResponse(
            id=entry.id,
            prompt_name=entry.prompt_name,
            agent_code=entry.agent_code,
            source=entry.source,
            metadata_extra=entry.metadata_extra or {},
            active=entry.active,
            tenant_id=entry.tenant_id,
            input_context=entry.input_context or {},
            expected_output=entry.expected_output,
            quality_score=entry.quality_score,
            created_at=entry.created_at.isoformat() if entry.created_at else None,
            updated_at=entry.updated_at.isoformat() if entry.updated_at else None,
        )


@router.post(
    "/v1/datasets/{agent_code}/mine",
    response_model=MiningTriggerResponse,
    status_code=202,
)
async def trigger_mining(
    agent_code: str,
    decision: Decision = Depends(require_permission(Permission.TRIGGER_OPTIMIZATION)),
):
    """AC-2: Trigger golden dataset mining task, returns 202."""
    from app.registries.prompt_catalog import AGENT_PORTS

    if agent_code not in AGENT_PORTS:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown agent_code: '{agent_code}'"},
        )

    from app.tasks.mine_golden_examples import mine_golden_examples

    try:
        task = mine_golden_examples.delay()
    except Exception as exc:
        logger.error("Failed to enqueue mining task: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Mining task broker unavailable"},
        )

    return MiningTriggerResponse(
        task_id=task.id,
        agent_code=agent_code,
        status="ACCEPTED",
        message=f"Platform-wide mining task queued (triggered via {agent_code})",
    )


@router.put(
    "/v1/datasets/{agent_code}/{entry_id}",
    response_model=GoldenDatasetResponse,
)
async def update_dataset_entry(
    agent_code: str,
    entry_id: int,
    request: GoldenDatasetUpdateRequest,
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.REGISTER)),
):
    """Update a golden dataset entry."""
    from sqlalchemy import select

    from app.models.database import async_session_factory
    from app.models.golden_dataset import GoldenDataset
    from app.registries.prompt_catalog import AGENT_PORTS

    if agent_code not in AGENT_PORTS:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown agent_code: '{agent_code}'"},
        )

    async with async_session_factory() as session:
        filters = [
            GoldenDataset.id == entry_id,
            GoldenDataset.agent_code == agent_code,
            GoldenDataset.active.is_(True),
        ]
        if x_tenant_id:
            filters.append(GoldenDataset.tenant_id.in_([x_tenant_id, None]))
        stmt = select(GoldenDataset).where(*filters)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Dataset entry {entry_id} not found"},
            )

        # Apply partial update
        update_data = request.model_dump(exclude_none=True)
        for field_name, value in update_data.items():
            setattr(row, field_name, value)

        await session.commit()
        await session.refresh(row)

        return GoldenDatasetResponse(
            id=row.id,
            prompt_name=row.prompt_name,
            agent_code=row.agent_code,
            source=row.source,
            metadata_extra=row.metadata_extra or {},
            active=row.active,
            tenant_id=row.tenant_id,
            input_context=row.input_context or {},
            expected_output=row.expected_output,
            quality_score=row.quality_score,
            created_at=row.created_at.isoformat() if row.created_at else None,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )


@router.delete("/v1/datasets/{agent_code}/{entry_id}", response_model=None)
async def delete_dataset_entry(
    agent_code: str,
    entry_id: int,
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.MODIFY_CONFIG)),
):
    """AC-1: Soft-delete a golden dataset entry (sets active=false)."""
    from sqlalchemy import select

    from app.models.database import async_session_factory
    from app.models.golden_dataset import GoldenDataset
    from app.registries.prompt_catalog import AGENT_PORTS

    if agent_code not in AGENT_PORTS:
        return JSONResponse(
            status_code=404,
            content={"detail": f"Unknown agent_code: '{agent_code}'"},
        )

    async with async_session_factory() as session:
        filters = [
            GoldenDataset.id == entry_id,
            GoldenDataset.agent_code == agent_code,
            GoldenDataset.active.is_(True),
        ]
        if x_tenant_id:
            filters.append(GoldenDataset.tenant_id.in_([x_tenant_id, None]))
        stmt = select(GoldenDataset).where(*filters)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Dataset entry {entry_id} not found"},
            )

        row.active = False
        await session.commit()

    return JSONResponse(
        status_code=200,
        content={"detail": f"Dataset entry {entry_id} deactivated"},
    )


@router.get("/v1/config/dataset-size", response_model=None)
async def get_dataset_size(
    x_tenant_id: str = Header(default=None, alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.VIEW)),
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
    request: DatasetSizeConfigRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    decision: Decision = Depends(require_permission(Permission.MODIFY_CONFIG)),
):
    """Set the golden dataset size limit for a tenant (AC-3: validates [3, 50])."""
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
async def approve_optimization_run(
    run_id: str,
    request: ApprovalRequest,
    decision: Decision = Depends(require_permission(Permission.APPROVE)),
):
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

        # Start canary deployment after approval
        prompt_name = progress.get("prompt_name", "")
        agent_code = progress.get("agent_code", "")
        if canary_manager and mlflow_registry and prompt_name:
            try:
                prompt_info = mlflow_registry.get_prompt(prompt_name)
                if prompt_info:
                    prod_info = None
                    if lifecycle_manager:
                        prod_info = lifecycle_manager.get_production_version(
                            prompt_name
                        )
                    prod_version = (
                        prod_info.version
                        if prod_info
                        else max(1, prompt_info.version - 1)
                    )
                    await canary_manager.start_canary(
                        prompt_name=prompt_name,
                        canary_version=prompt_info.version,
                        production_version=prod_version,
                        agent_code=agent_code,
                    )
                    logger.info(
                        "Canary started after approval: prompt=%s, v%d vs v%d",
                        prompt_name,
                        prompt_info.version,
                        prod_version,
                    )
            except Exception as exc:
                logger.warning("Failed to start canary after approval: %s", exc)

        return ApprovalResponse(
            run_id=decision.run_id,
            decision=decision.decision,
            approved_by=decision.approved_by,
            decided_at=decision.decided_at.isoformat(),
        )
    finally:
        await cache.close()


@router.post("/v1/optimize/runs/{run_id}/reject", response_model=ApprovalResponse)
async def reject_optimization_run(
    run_id: str,
    request: RejectionRequest,
    decision: Decision = Depends(require_permission(Permission.APPROVE)),
):
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
async def delete_tenant_override_endpoint(
    name: str,
    tenant_id: str,
    decision: Decision = Depends(require_permission(Permission.DELETE_OVERRIDE)),
):
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


# ── Canary metrics + dashboard endpoints ──


@router.post("/v1/canary/start", response_model=None, status_code=201)
async def start_canary(request: Request):
    """Start a canary deployment for a prompt version."""
    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )
    body = await request.json()
    prompt_name = body.get("prompt_name")
    canary_version = body.get("canary_version")
    production_version = body.get("production_version")
    agent_code = body.get("agent_code", "")
    if not prompt_name or canary_version is None or production_version is None:
        return JSONResponse(
            status_code=400,
            content={
                "detail": "prompt_name, canary_version, and production_version required"
            },
        )
    state = await canary_manager.start_canary(
        prompt_name, int(canary_version), int(production_version), agent_code
    )
    return JSONResponse(
        status_code=201,
        content={
            "prompt_name": state.prompt_name,
            "canary_version": state.canary_version,
            "production_version": state.production_version,
            "started_at": state.started_at.isoformat(),
            "expires_at": state.expires_at.isoformat(),
            "active": state.active,
        },
    )


@router.post(
    "/v1/prompts/{name}/versions/{version}/metrics",
    response_model=None,
    status_code=201,
)
async def record_canary_metric(
    name: str,
    version: int,
    raw_request: Request,
):
    """Record a scorer metric for a canary or production version."""
    from app.api.schemas import CanaryMetricRecordRequest

    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )
    data = await raw_request.json()
    req = CanaryMetricRecordRequest(**data)
    await canary_manager.record_canary_metric(name, version, req.scorer_name, req.score)
    return JSONResponse(
        status_code=201,
        content={
            "detail": f"Metric '{req.scorer_name}' recorded for {name} v{version}"
        },
    )


@router.get("/v1/canary/active", response_model=None)
async def list_active_canaries():
    """List all currently active canary deployments."""
    from datetime import datetime, timezone

    from app.api.schemas import ActiveCanariesResponse, CanaryDeploymentInfo

    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )

    canaries = await canary_manager.list_active_canaries()
    now = datetime.now(timezone.utc)
    items = [
        CanaryDeploymentInfo(
            prompt_name=c.prompt_name,
            canary_version=c.canary_version,
            production_version=c.production_version,
            agent_code=c.agent_code,
            started_at=c.started_at.isoformat(),
            expires_at=c.expires_at.isoformat(),
            time_remaining_hours=max(0, (c.expires_at - now).total_seconds() / 3600),
            active=c.active,
        )
        for c in canaries
    ]
    return ActiveCanariesResponse(canaries=items)


@router.get("/v1/canary/{prompt_name}/metrics", response_model=None)
async def get_canary_metrics_comparison(prompt_name: str):
    """Get side-by-side metrics comparison for canary vs production."""
    from app.api.schemas import CanaryMetricsComparison

    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )

    comparison = await canary_manager.get_canary_comparison(prompt_name)
    if comparison is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No active canary for '{prompt_name}'"},
        )
    return CanaryMetricsComparison(**comparison)


@router.get("/v1/canary/history", response_model=None)
async def get_canary_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    """List canary deployment outcomes, paginated.

    Reads from PostgreSQL (durable). Falls back to Redis if PostgreSQL
    has no data yet (pre-migration history).
    """
    from app.api.schemas import CanaryHistoryEntry, CanaryHistoryResponse

    # Try PostgreSQL first
    try:
        from sqlalchemy import func, select

        from app.models.canary_history import CanaryHistory
        from app.models.database import async_session_factory

        async with async_session_factory() as session:
            count_stmt = select(func.count()).select_from(CanaryHistory)
            total = (await session.execute(count_stmt)).scalar() or 0

            if total > 0:
                offset = (page - 1) * page_size
                stmt = (
                    select(CanaryHistory)
                    .order_by(CanaryHistory.ended_at.desc())
                    .offset(offset)
                    .limit(page_size)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                entries = [
                    CanaryHistoryEntry(
                        prompt_name=row.prompt_name,
                        canary_version=row.canary_version,
                        started_at=row.started_at.isoformat() if row.started_at else "",
                        ended_at=row.ended_at.isoformat() if row.ended_at else "",
                        outcome=row.outcome,
                        final_regression_pct=row.final_regression_pct,
                    )
                    for row in rows
                ]
                return CanaryHistoryResponse(
                    history=entries, total=total, page=page, page_size=page_size
                )
    except Exception:
        pass  # Fall through to Redis

    # Fallback: read from Redis (pre-migration data)
    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )

    all_history = await canary_manager.list_canary_history()
    total = len(all_history)
    start = (page - 1) * page_size
    page_items = all_history[start : start + page_size]
    entries = [CanaryHistoryEntry(**h) for h in page_items]
    return CanaryHistoryResponse(
        history=entries, total=total, page=page, page_size=page_size
    )


@router.post("/v1/canary/{prompt_name}/promote", response_model=None)
async def promote_canary(
    prompt_name: str,
    decision: Decision = Depends(require_permission(Permission.PROMOTE)),
):
    """Force-promote an active canary to production.

    Requires PROMOTE permission. Records outcome in canary history
    and transitions the prompt lifecycle to PRODUCTION.
    """
    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )

    state = await canary_manager.get_canary_state(prompt_name)
    if state is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No active canary for {prompt_name}"},
        )

    promoted = await canary_manager.promote_canary(prompt_name)
    if not promoted:
        return JSONResponse(
            status_code=500, content={"detail": "Promotion failed"}
        )

    logger.info(
        "Admin force-promoted canary: %s v%d (was production v%d)",
        prompt_name,
        state.canary_version,
        state.production_version,
    )
    return {
        "status": "promoted",
        "prompt_name": prompt_name,
        "canary_version": state.canary_version,
        "production_version": state.production_version,
    }


@router.post("/v1/canary/{prompt_name}/rollback", response_model=None)
async def rollback_canary(
    prompt_name: str,
    decision: Decision = Depends(require_permission(Permission.PROMOTE)),
):
    """Force-rollback an active canary.

    Requires PROMOTE permission. Records outcome in canary history
    and transitions the prompt lifecycle to ROLLED_BACK.
    """
    if canary_manager is None:
        return JSONResponse(
            status_code=503, content={"detail": "Canary manager not initialized"}
        )

    state = await canary_manager.get_canary_state(prompt_name)
    if state is None:
        return JSONResponse(
            status_code=404,
            content={"detail": f"No active canary for {prompt_name}"},
        )

    rolled_back = await canary_manager.rollback_canary(prompt_name)
    if not rolled_back:
        return JSONResponse(
            status_code=500, content={"detail": "Rollback failed"}
        )

    logger.info(
        "Admin force-rolled-back canary: %s v%d (reverted to production v%d)",
        prompt_name,
        state.canary_version,
        state.production_version,
    )
    return {
        "status": "rolled_back",
        "prompt_name": prompt_name,
        "canary_version": state.canary_version,
        "production_version": state.production_version,
    }


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

    from app.models.database import async_session_factory

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        mgr = TenantConfigManager(cache, db_session_factory=async_session_factory)
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
    request: TenantConfigUpdateRequest,
    x_tenant_id: str = Header(default="", alias="X-Tenant-ID"),
):
    """Update tenant optimization configuration keys."""
    from app.api.schemas import TenantOptimizationConfig

    if x_tenant_id and tenant_id != x_tenant_id:
        return JSONResponse(
            status_code=403,
            content={"detail": "Cannot modify another tenant's configuration"},
        )
    from app.cache.prompt_cache import PromptCacheManager
    from app.cache.tenant_config import TenantConfigManager
    from app.core.config import settings
    from app.models.database import async_session_factory

    cache = PromptCacheManager(redis_url=settings.PROMPT_CACHE_REDIS_URL)
    await cache.connect()
    try:
        mgr = TenantConfigManager(cache, db_session_factory=async_session_factory)
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
