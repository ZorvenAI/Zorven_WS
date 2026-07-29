"""HTTP endpoints for the Campaign Optimization Agent service.

Endpoints:
    GET  /health                                — Liveness probe + celery status
    GET  /v1/campaigns/{id}/recommendations     — List pending recommendations
    POST /v1/recommendations/{id}/approve       — Approve recommendation
    POST /v1/recommendations/{id}/reject        — Reject recommendation
    POST /v1/recommendations/{id}/modify        — Modify and approve
    POST /v1/recommendations/batch-approve      — Batch approve all pending
    GET  /v1/campaigns/{id}/performance         — Current performance metrics
    POST /v1/tick/trigger                       — Manually trigger optimization tick
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from app.api.auth import verify_service_token
from app.core.config import settings
from app.api.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    BatchApprovalRequest,
    CampaignPerformanceResponse,
    HealthResponse,
    RecommendationResponse,
    TickStatusResponse,
    TriggerTickRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health(request: Request) -> HealthResponse:
    """Liveness probe with Celery status."""
    celery_status = "unknown"
    try:
        from app.celery_app import celery_app

        inspect = celery_app.control.inspect(timeout=2.0)
        ping_result = inspect.ping()
        celery_status = "ok" if ping_result else "no_workers"
    except Exception as exc:
        logger.debug("Celery health check failed: %s", exc)
        celery_status = "unavailable"

    return HealthResponse(
        status="ok",
        service="campaign-optimization-agent",
        version="1.0.0",
        celery_status=celery_status,
    )


@router.get("/health/diagnostics")
async def diagnostics(request: Request) -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)

    issues = []
    if not has_anthropic:
        issues.append("COA_ANTHROPIC_API_KEY is missing — running in STUB MODE")

    executor = getattr(request.app.state, "executor", None)

    return {
        "service": "campaign-optimization-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.ANTHROPIC_MODEL,
        "keys_configured": {
            "COA_ANTHROPIC_API_KEY": has_anthropic,
        },
        "issues": issues,
        "executor_initialized": executor is not None,
    }


@router.get("/v1/campaigns/{campaign_id}/recommendations")
async def list_recommendations(
    campaign_id: str,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> list[RecommendationResponse]:
    """List pending recommendations for a campaign."""
    approval_handler = getattr(request.app.state, "approval_handler", None)
    if approval_handler is None:
        return []
    try:
        recs = await approval_handler.list_pending_recommendations(
            campaign_id=campaign_id, tenant_id=x_tenant_id
        )
        return [RecommendationResponse(**r) for r in recs]
    except Exception as exc:
        logger.error("Failed to list recommendations: %s", exc)
        return []


@router.post("/v1/recommendations/{rec_id}/approve")
async def approve_recommendation(
    rec_id: str,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> ApprovalResponse:
    """Approve a single recommendation."""
    approval_handler = getattr(request.app.state, "approval_handler", None)
    if approval_handler is None:
        return ApprovalResponse(recommendation_id=rec_id, status="error")
    try:
        result = await approval_handler.approve_recommendation(
            rec_id=rec_id,
            approved_by="api",
            user_role="ADMIN",
        )
        return ApprovalResponse(
            recommendation_id=rec_id,
            status=result.get("status", "approved"),
            executed=result.get("executed", False),
            execution_result=result.get("execution_result"),
        )
    except Exception as exc:
        logger.error("Failed to approve recommendation %s: %s", rec_id, exc)
        return ApprovalResponse(recommendation_id=rec_id, status="error")


@router.post("/v1/recommendations/{rec_id}/reject")
async def reject_recommendation(
    rec_id: str,
    request: Request,
    payload: ApprovalRequest | None = None,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> ApprovalResponse:
    """Reject a single recommendation."""
    approval_handler = getattr(request.app.state, "approval_handler", None)
    if approval_handler is None:
        return ApprovalResponse(recommendation_id=rec_id, status="error")
    try:
        reason = payload.feedback if payload else ""
        rejected_by = payload.approved_by if payload else "api"
        result = await approval_handler.reject_recommendation(
            rec_id=rec_id,
            reason=reason,
            rejected_by=rejected_by,
        )
        return ApprovalResponse(
            recommendation_id=rec_id,
            status=result.get("status", "rejected"),
            executed=False,
        )
    except Exception as exc:
        logger.error("Failed to reject recommendation %s: %s", rec_id, exc)
        return ApprovalResponse(recommendation_id=rec_id, status="error")


@router.post("/v1/recommendations/{rec_id}/modify")
async def modify_recommendation(
    rec_id: str,
    payload: ApprovalRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> ApprovalResponse:
    """Modify and approve a recommendation."""
    approval_handler = getattr(request.app.state, "approval_handler", None)
    if approval_handler is None:
        return ApprovalResponse(recommendation_id=rec_id, status="error")
    try:
        result = await approval_handler.modify_recommendation(
            rec_id=rec_id,
            modified_values=payload.modified_values or {},
            approved_by=payload.approved_by or "api",
        )
        return ApprovalResponse(
            recommendation_id=rec_id,
            status=result.get("status", "modified_and_approved"),
            executed=result.get("executed", False),
            execution_result=result.get("execution_result"),
        )
    except Exception as exc:
        logger.error("Failed to modify recommendation %s: %s", rec_id, exc)
        return ApprovalResponse(recommendation_id=rec_id, status="error")


@router.post("/v1/recommendations/batch-approve")
async def batch_approve(
    payload: BatchApprovalRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
) -> list[ApprovalResponse]:
    """Batch approve all pending recommendations for a campaign."""
    approval_handler = getattr(request.app.state, "approval_handler", None)
    if approval_handler is None:
        return []
    try:
        results = await approval_handler.batch_approve(
            campaign_id=payload.campaign_id,
            tenant_id=payload.tenant_id,
            approved_by=payload.approved_by or "api",
        )
        return [
            ApprovalResponse(
                recommendation_id=r.get("recommendation_id", ""),
                status=r.get("status", "approved"),
                executed=r.get("executed", False),
                execution_result=r.get("execution_result"),
            )
            for r in results
        ]
    except Exception as exc:
        logger.error("Failed to batch approve: %s", exc)
        return []


@router.get("/v1/campaigns/{campaign_id}/performance")
async def get_campaign_performance(
    campaign_id: str,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> CampaignPerformanceResponse:
    """Get current performance metrics for a campaign."""
    redis_manager = getattr(request.app.state, "redis_manager", None)
    if redis_manager is None:
        return CampaignPerformanceResponse(campaign_id=campaign_id)
    try:
        perf = await redis_manager.get_performance_history(
            tenant_id=x_tenant_id, campaign_id=campaign_id
        )
        return CampaignPerformanceResponse(
            campaign_id=campaign_id,
            metrics=perf.get("metrics", {}),
            health=perf.get("health", "unknown"),
            trends=perf.get("trends", {}),
        )
    except Exception as exc:
        logger.error("Failed to get performance for %s: %s", campaign_id, exc)
        return CampaignPerformanceResponse(campaign_id=campaign_id)


@router.post("/v1/execute")
async def execute(
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Pipeline execution endpoint — called by the orchestrator.

    Registers the campaign for continuous optimization and triggers
    the first optimization tick.  Returns a summary suitable for
    ``result_data`` propagation via the orchestrator callback.
    """
    body = await request.json()
    previous_outputs = body.get("previous_outputs", {})
    config = body.get("config", {})
    tenant_context = body.get("tenant_context", {})
    tenant_id = x_tenant_id or tenant_context.get("tenant_id", "")

    # Extract campaign info from ad_publishing output
    ad_pub = previous_outputs.get("ad_publishing", {})
    result_data = ad_pub.get("result_data", {})
    campaign_id = result_data.get("campaign_id") or ad_pub.get("campaign_id") or ""
    campaign_name = (
        result_data.get("campaign_name")
        or ad_pub.get("campaign_name")
        or "Unknown Campaign"
    )
    meta_campaign_id = (
        result_data.get("meta_campaign_id") or ad_pub.get("meta_campaign_id") or ""
    )

    # Register campaign for optimization via Django backend
    registered = False
    callback_client = getattr(request.app.state, "callback_client", None)
    if callback_client and campaign_id:
        try:
            await callback_client.register_campaign_for_optimization(
                tenant_id=tenant_id,
                campaign_id=campaign_id,
            )
            registered = True
        except Exception as exc:
            logger.warning(
                "Could not register campaign %s for optimization: %s",
                campaign_id,
                exc,
            )

    # Trigger initial optimization tick for this campaign
    tick_triggered = False
    try:
        from app.tasks import run_optimization_tick

        task = run_optimization_tick.delay(
            campaign_age_min_days=0,
            campaign_age_max_days=7,
        )
        tick_triggered = True
        tick_id = task.id
    except Exception as exc:
        logger.warning("Could not trigger initial tick: %s", exc)
        tick_id = ""

    optimization_mode = config.get("optimization_mode", "manual")

    summary = {
        "status": "optimization_activated",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "meta_campaign_id": meta_campaign_id,
        "optimization_mode": optimization_mode,
        "registered": registered,
        "initial_tick_triggered": tick_triggered,
        "tick_id": tick_id,
        "schedule": {
            "hourly": "campaigns < 7 days old",
            "four_hourly": "campaigns 7-30 days old",
            "daily": "campaigns > 30 days old",
        },
        "message": (
            f"Campaign '{campaign_name}' registered for continuous "
            f"optimization in {optimization_mode} mode. "
            f"Performance will be monitored on an adaptive schedule."
        ),
    }

    return {
        "continuous_optimization": summary,
        "result_data": {
            "continuous_optimization": summary,
        },
    }


@router.post("/v1/tick/trigger")
async def trigger_tick(
    request: Request,
    payload: TriggerTickRequest | None = None,
    _token: str = Depends(verify_service_token),
) -> dict:
    """Manually trigger an optimization tick.

    Synchronously waits up to 15s for the Celery task to finish (ticks
    typically complete in <1s). Returns the full tick result including
    per-campaign skip reasons so callers can display them immediately.
    If the task does not finish in time, returns a pending status with
    the task id.
    """
    import asyncio

    try:
        from app.tasks import run_optimization_tick

        age_min = payload.campaign_age_min_days if payload else None
        age_max = payload.campaign_age_max_days if payload else None

        task = run_optimization_tick.delay(
            campaign_age_min_days=age_min,
            campaign_age_max_days=age_max,
        )

        # Wait up to 15s for result without blocking event loop
        for _ in range(30):  # 30 * 0.5s = 15s
            if task.ready():
                break
            await asyncio.sleep(0.5)

        if task.ready():
            try:
                result = task.get(timeout=1)
                return {
                    "tick_id": result.get("tick_id", task.id),
                    "status": "completed",
                    "campaigns_processed": result.get("campaigns_processed", 0),
                    "recommendations_generated": result.get(
                        "recommendations_generated", 0
                    ),
                    "actions_executed": result.get("actions_executed", 0),
                    "campaign_results": result.get("campaign_results", []),
                    "elapsed_ms": result.get("elapsed_ms", 0),
                }
            except Exception as exc:
                logger.error("Failed to retrieve task result: %s", exc)
                return {
                    "tick_id": task.id,
                    "status": "error",
                    "error": str(exc),
                }

        return {
            "tick_id": task.id,
            "status": "pending",
            "message": "Tick is still running in the background",
        }
    except Exception as exc:
        logger.error("Failed to trigger tick: %s", exc)
        return {"tick_id": "error", "status": "error", "error": str(exc)}
