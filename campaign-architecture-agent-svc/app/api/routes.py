"""API routes for the Campaign Architecture Agent."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from app.api.auth import verify_service_token
from app.api.schemas import ExecuteRequest
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    """Health check — no auth required."""
    return {"status": "ok", "service": "campaign-architecture-agent"}


@router.get("/health/diagnostics")
async def diagnostics(request: Request) -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)

    issues = []
    if not has_anthropic:
        issues.append("CAA_ANTHROPIC_API_KEY is missing — running in STUB MODE")

    executor = getattr(request.app.state, "executor", None)

    return {
        "service": "campaign-architecture-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.ANTHROPIC_MODEL,
        "keys_configured": {
            "CAA_ANTHROPIC_API_KEY": has_anthropic,
        },
        "issues": issues,
        "executor_initialized": executor is not None,
    }


@router.post("/v1/execute")
async def execute(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Execute campaign architecture analysis."""
    executor = getattr(request.app.state, "executor", None)

    if executor is None:
        return _stub_response(payload.input_prompt)

    tenant_id = x_tenant_id
    if not tenant_id:
        tc = payload.tenant_context
        if isinstance(tc, dict):
            tenant_id = tc.get("tenant_id", "")
        else:
            tenant_id = tc.tenant_id

    tenant_context = payload.tenant_context
    if isinstance(tenant_context, dict):
        pass  # already a dict
    else:
        tenant_context = tenant_context.model_dump()

    result = await executor.execute(
        prompt=payload.input_prompt,
        input_context=payload.input_context,
        tenant_context=tenant_context,
        config=payload.config,
        previous_outputs=payload.previous_outputs,
        tenant_id=tenant_id,
    )
    return result


@router.post("/v1/campaign-blueprint")
async def campaign_blueprint(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for campaign blueprint generation."""
    executor = getattr(request.app.state, "executor", None)

    if executor is None:
        return _stub_response(payload.input_prompt)

    tenant_id = x_tenant_id
    if not tenant_id:
        tc = payload.tenant_context
        if isinstance(tc, dict):
            tenant_id = tc.get("tenant_id", "")
        else:
            tenant_id = tc.tenant_id

    result = await executor.execute(
        prompt=payload.input_prompt,
        input_context=payload.input_context,
        tenant_context=(
            payload.tenant_context
            if isinstance(payload.tenant_context, dict)
            else payload.tenant_context.model_dump()
        ),
        config=payload.config,
        previous_outputs=payload.previous_outputs,
        tenant_id=tenant_id,
    )
    return result


def _stub_response(prompt: str) -> dict[str, Any]:
    """Return a stub response when executor is not initialized."""
    return {
        "query": prompt,
        "blueprint": {},
        "funnel_map": {},
        "targeting_specs": [],
        "placement_budget": {},
        "test_plan": {},
        "kpi_targets": {},
        "performance_projections": {},
        "risk_assessment": {},
        "creative_briefs": [],
        "special_ad_category": "",
        "meta_api_compatible": False,
        "confidence_score": 0.0,
        "findings": [
            "STUB MODE: CAA executor not initialized — "
            "CAA_ANTHROPIC_API_KEY is missing or invalid. "
            "Hit /health/diagnostics for details."
        ],
        "recommendations": [],
        "sources": [],
        "wf1_context_used": False,
        "wf2_context_used": False,
        "bpa_context_used": False,
        "company_context_used": False,
        "tavily_benchmarks_used": False,
        "odoo_data_used": False,
        "rag_learnings_used": False,
        "gcs_uri": "",
        "execution_time_ms": 0,
    }
