"""API routes for the Creative Generation Agent."""

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
    return {"status": "ok", "service": "creative-generation-agent"}


@router.get("/health/diagnostics")
async def diagnostics(request: Request) -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence on Railway."""
    api_key = settings.ANTHROPIC_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)

    issues = []
    if not has_anthropic:
        issues.append("CGA_ANTHROPIC_API_KEY is missing — running in STUB MODE")

    executor = getattr(request.app.state, "executor", None)

    return {
        "service": "creative-generation-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.ANTHROPIC_MODEL,
        "keys_configured": {
            "CGA_ANTHROPIC_API_KEY": has_anthropic,
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
    """Execute creative generation for a campaign."""
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
        pass
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


@router.post("/v1/creative")
async def creative(
    payload: ExecuteRequest,
    request: Request,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header("", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for creative generation."""
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
        "creative_package": {},
        "ad_set_packages": [],
        "ad_units": [],
        "generated_images": [],
        "hooks": [],
        "copy_variants": [],
        "ctas": [],
        "compliance_results": [],
        "creative_profiles": [],
        "total_images_generated": 0,
        "total_images_refined": 0,
        "image_gen_cost_usd": 0.0,
        "compliance_pass_rate": 0.0,
        "creative_quality_score": 0.0,
        "confidence_score": 0.0,
        "findings": [
            "STUB MODE: CGA executor not initialized — "
            "CGA_ANTHROPIC_API_KEY is missing or invalid. "
            "Hit /health/diagnostics for details."
        ],
        "recommendations": [],
        "sources": [],
        "caa_context_used": False,
        "wf1_context_used": False,
        "bpa_context_used": False,
        "bpv_context_used": False,
        "nta_context_used": False,
        "bsa_context_used": False,
        "baa_context_used": False,
        "company_context_used": False,
        "image_gen_failed": False,
        "gcs_uri": "",
        "execution_time_ms": 0,
    }
