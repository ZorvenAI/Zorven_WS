"""HTTP routes for Intelligence Loop Agent."""

import logging

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_service_token
from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(service=settings.SERVICE_NAME)


@router.get("/health/diagnostics")
async def diagnostics(request: Request) -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)

    issues = []
    if not has_anthropic:
        issues.append("ILA_ANTHROPIC_API_KEY is missing — running in STUB MODE")

    extractor = getattr(request.app.state, "extractor", None)

    return {
        "service": "intelligence-loop-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.ANTHROPIC_MODEL,
        "keys_configured": {
            "ILA_ANTHROPIC_API_KEY": has_anthropic,
        },
        "issues": issues,
        "executor_initialized": extractor is not None,
    }


@router.post(
    "/v1/execute",
    response_model=ExecuteResponse,
    dependencies=[Depends(require_service_token)],
)
async def execute(payload: ExecuteRequest, request: Request) -> ExecuteResponse:
    """Synchronous extract endpoint called by pipeline-orchestrator-svc."""
    extractor = request.app.state.extractor
    redis_manager = request.app.state.redis_manager
    audit = request.app.state.audit_producer

    # Idempotency
    is_first = await redis_manager.set_dedup(payload.tenant_id or "", payload.job_id)
    if not is_first:
        logger.info("Duplicate execute job_id=%s — returning skipped", payload.job_id)

    await redis_manager.mark_status(payload.tenant_id or "", payload.job_id, "running")

    report = await extractor.extract(
        job_id=payload.job_id,
        tenant_id=payload.tenant_id,
        state=payload.state,
        context=payload.context,
        config=payload.config,
    )

    await audit.send(
        {
            "event": "intelligence.extracted",
            "job_id": payload.job_id,
            "tenant_id": payload.tenant_id,
            "intelligence_id": report.intelligence_id,
            "learning_count": len(report.learnings),
        }
    )

    await redis_manager.mark_status(
        payload.tenant_id or "", payload.job_id, "completed"
    )

    return ExecuteResponse(
        status="success" if is_first else "skipped",
        job_id=payload.job_id,
        intelligence_report=report,
    )
