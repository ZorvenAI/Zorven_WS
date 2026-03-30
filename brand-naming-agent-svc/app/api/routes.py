"""API routes for the Naming & Tagline Agent."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from app.api.auth import verify_service_token
from app.api.schemas import ExecuteRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    """Health check — no auth required."""
    return {"status": "ok", "service": "brand-naming-agent"}


@router.post("/v1/execute")
async def execute(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Execute brand naming & tagline analysis."""
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


@router.post("/v1/naming")
async def naming(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for naming analysis."""
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
            payload.tenant_context if isinstance(payload.tenant_context, dict)
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
        "name_candidates": [],
        "shortlisted_names": [],
        "taglines": [],
        "naming_brief": {},
        "availability_results": {},
        "scoring_summary": {},
        "confidence_score": 0.0,
        "findings": ["NTA executor not initialized (LLM key missing?)"],
        "recommendations": [],
        "sources": [],
        "wf1_context_used": False,
        "bpa_context_used": False,
        "bpv_context_used": False,
        "baa_context_used": False,
        "execution_time_ms": 0,
    }
