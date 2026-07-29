"""API routes for the Brand Story Agent."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from app.api.auth import verify_service_token
from app.core.config import settings
from app.api.schemas import ExecuteRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    """Health check — no auth required."""
    return {"status": "ok", "service": "brand-story-agent"}


@router.get("/health/diagnostics")
async def diagnostics(request: Request) -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)

    issues = []
    if not has_anthropic:
        issues.append("BSA_ANTHROPIC_API_KEY is missing — running in STUB MODE")

    executor = getattr(request.app.state, "executor", None)

    return {
        "service": "brand-story-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.ANTHROPIC_MODEL,
        "keys_configured": {
            "BSA_ANTHROPIC_API_KEY": has_anthropic,
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
    """Execute brand story & narrative analysis."""
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


@router.post("/v1/story")
async def story(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for brand story analysis."""
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
        "origin_story": {},
        "mission_vision": {},
        "pitches": {},
        "channel_narratives": {},
        "story_style_guide": {},
        "subbrand_stories": [],
        "narrative_package": {},
        "wf2_strategy_summary": {},
        "confidence_score": 0.0,
        "findings": ["STUB MODE: BSA_ANTHROPIC_API_KEY is not configured. Set the environment variable and redeploy."],
        "recommendations": [],
        "sources": [],
        "wf1_context_used": False,
        "bpa_context_used": False,
        "bpv_context_used": False,
        "baa_context_used": False,
        "nta_context_used": False,
        "gcs_uri": "",
        "execution_time_ms": 0,
    }
