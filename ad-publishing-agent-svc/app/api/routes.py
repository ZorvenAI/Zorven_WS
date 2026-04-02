"""HTTP endpoints for the Ad Publishing Agent service.

Endpoints:
    GET  /health                            — Liveness probe
    POST /v1/execute                        — Run phases 1-4, return approval request
    POST /v1/approve                        — Process human approval, run phases 6-7
    GET  /v1/approvals/{tenant_id}          — List pending approvals
    GET  /v1/approvals/{tenant_id}/{id}     — Get approval details + preview
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from app.api.auth import verify_service_token
from app.api.schemas import ApprovalRequest, ExecuteRequest

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok", "service": "ad-publishing-agent"}


@router.post("/v1/execute")
async def execute(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Run phases 1-4: create campaign structure + generate previews.

    Returns status="awaiting_approval" with preview data for human review.
    """
    executor = getattr(request.app.state, "executor", None)

    # Extract tenant_id from header or payload
    tenant_id = x_tenant_id
    if not tenant_id:
        tc = payload.tenant_context
        if isinstance(tc, dict):
            tenant_id = tc.get("tenant_id", "")
        else:
            tenant_id = tc.tenant_id

    job_id = payload.input_context.get("job_id", "")

    if executor is None:
        logger.warning("Executor not initialized — returning stub response")
        return {
            "status": "awaiting_approval",
            "approval_request_id": "stub-approval-id",
            "preview_data": {},
            "is_production": False,
            "sandbox_mode": True,
            "findings": [
                "Ad Publishing Agent not fully initialized. "
                "Returning stub response."
            ],
            "recommendations": [
                "Check service logs for initialization errors."
            ],
            "execution_time_ms": 0,
        }

    # Build tenant_context dict
    tc = payload.tenant_context
    tenant_ctx = tc if isinstance(tc, dict) else tc.model_dump()

    result = await executor.execute(
        prompt=payload.input_prompt,
        input_context=payload.input_context,
        tenant_context=tenant_ctx,
        config=payload.config,
        previous_outputs=payload.previous_outputs,
        tenant_id=tenant_id,
        job_id=job_id,
    )
    return result


@router.post("/v1/approve")
async def approve(
    payload: ApprovalRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Process human approval decision.

    On approve: runs phases 6-7 (publish + verify).
    On reject: marks as rejected.
    """
    executor = getattr(request.app.state, "executor", None)
    approval_mgr = getattr(request.app.state, "approval_manager", None)

    if executor is None or approval_mgr is None:
        return {
            "status": "error",
            "error": "Service not fully initialized",
        }

    # Resolve tenant_id: prefer header, fall back to approval record
    tenant_id = x_tenant_id
    if not tenant_id:
        req_data = await approval_mgr.get_approval_request(
            payload.approval_request_id, ""
        )
        if req_data:
            tenant_id = req_data.get("tenant_id", "")

    if not tenant_id:
        return {
            "status": "error",
            "error": "tenant_id required (X-Tenant-ID header or approval record)",
        }

    # Process the approval decision — user identity from payload
    approval_result = await approval_mgr.process_approval(
        request_id=payload.approval_request_id,
        tenant_id=tenant_id,
        decision=payload.decision,
        approved_ad_sets=payload.approved_ad_sets,
        feedback=payload.feedback,
        approved_by=payload.approved_by,
        user_role=payload.user_role,
        production_confirmed=payload.production_confirmed,
    )

    # If approved, continue to publishing (phases 6-7)
    if approval_result.get("status") in ("approved", "partial"):
        # Retrieve job_id from the approval request
        req_data = await approval_mgr.get_approval_request(
            payload.approval_request_id, tenant_id
        )
        job_id = req_data.get("job_id", "") if req_data else ""

        publish_result = await executor.resume_after_approval(
            approval_request_id=payload.approval_request_id,
            approval_result=approval_result,
            tenant_id=tenant_id,
            job_id=job_id,
        )
        return publish_result

    # Rejected, escalated, or error — return as-is
    return approval_result


@router.get("/v1/approvals/{tenant_id}")
async def list_approvals(
    tenant_id: str,
    request: Request,
    _token: str = Depends(verify_service_token),
) -> list[dict[str, Any]]:
    """List pending approval requests for a tenant."""
    approval_mgr = getattr(request.app.state, "approval_manager", None)
    if approval_mgr is None:
        return []
    return await approval_mgr.list_pending(tenant_id)


@router.get("/v1/approvals/{tenant_id}/{request_id}")
async def get_approval(
    tenant_id: str,
    request_id: str,
    request: Request,
    _token: str = Depends(verify_service_token),
) -> dict[str, Any]:
    """Get approval request details + preview."""
    approval_mgr = getattr(request.app.state, "approval_manager", None)
    if approval_mgr is None:
        return {"error": "Service not initialized"}
    result = await approval_mgr.get_approval_request(request_id, tenant_id)
    if result is None:
        return {"error": "Approval request not found"}
    return result
