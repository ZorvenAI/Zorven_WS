"""API endpoints for the Brand Architecture Agent service."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.auth import verify_service_token
from app.core.config import settings
from app.api.schemas import BAAResponse, ExecuteRequest
from app.services.baa_executor import BAAExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor, injected from main.py lifespan
executor: BAAExecutor | None = None
prompt_loader = None


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "service": "brand-architecture-agent"}


@router.get("/health/diagnostics")
async def diagnostics() -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)

    issues = []
    if not has_anthropic:
        issues.append("BAA_ANTHROPIC_API_KEY is missing — running in STUB MODE")

    return {
        "service": "brand-architecture-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.ANTHROPIC_MODEL,
        "keys_configured": {
            "BAA_ANTHROPIC_API_KEY": has_anthropic,
        },
        "issues": issues,
        "executor_initialized": executor is not None,
    }


async def _execute_architecture(
    payload: ExecuteRequest,
    tenant_id: str,
) -> dict[str, Any]:
    """Shared execution logic for /v1/execute and /v1/architecture."""
    if executor is None:
        logger.warning("Executor not initialized, returning stub response")
        return BAAResponse(
            query=payload.input_prompt,
            findings=["STUB MODE: BAA_ANTHROPIC_API_KEY is not configured. Set the environment variable and redeploy."],
            confidence_score=0.0,
        ).model_dump()

    result = await executor.execute(
        prompt=payload.input_prompt,
        input_context=payload.input_context,
        tenant_context=payload.tenant_context.model_dump(),
        config=payload.config,
        previous_outputs=payload.previous_outputs,
        tenant_id=tenant_id,
    )
    return result


@router.post("/v1/execute")
async def execute(
    payload: ExecuteRequest,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Execute brand architecture analysis (orchestrator dispatch endpoint)."""
    logger.info(
        "Execute request: tenant=%s, prompt=%.80s",
        x_tenant_id,
        payload.input_prompt,
    )
    return await _execute_architecture(payload, x_tenant_id)


@router.post("/v1/architecture")
async def architecture(
    payload: ExecuteRequest,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for brand architecture analysis."""
    logger.info(
        "Architecture request: tenant=%s, prompt=%.80s",
        x_tenant_id,
        payload.input_prompt,
    )
    return await _execute_architecture(payload, x_tenant_id)
