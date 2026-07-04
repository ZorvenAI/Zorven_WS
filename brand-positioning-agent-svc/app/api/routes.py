"""API endpoints for the Brand Positioning Agent service."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.auth import verify_service_token
from app.api.schemas import BPAResponse, ExecuteRequest
from app.services.bpa_executor import BPAExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor, injected from main.py lifespan
executor: BPAExecutor | None = None
prompt_loader = None


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "service": "brand-positioning-agent"}


async def _execute_positioning(
    payload: ExecuteRequest,
    tenant_id: str,
) -> dict[str, Any]:
    """Shared execution logic for /v1/execute and /v1/position."""
    if executor is None:
        logger.warning("Executor not initialized, returning stub response")
        return BPAResponse(
            query=payload.input_prompt,
            findings=["Service initializing — stub response"],
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
    """Execute brand positioning analysis (orchestrator dispatch endpoint)."""
    logger.info(
        "Execute request: tenant=%s, prompt=%.80s",
        x_tenant_id,
        payload.input_prompt,
    )
    return await _execute_positioning(payload, x_tenant_id)


@router.post("/v1/position")
async def position(
    payload: ExecuteRequest,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for brand positioning analysis."""
    logger.info(
        "Position request: tenant=%s, prompt=%.80s",
        x_tenant_id,
        payload.input_prompt,
    )
    return await _execute_positioning(payload, x_tenant_id)
