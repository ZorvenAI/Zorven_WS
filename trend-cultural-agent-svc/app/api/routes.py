"""API routes for the Trend & Cultural Insights Agent service."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.auth import verify_service_token
from app.api.schemas import ExecuteRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# Executor is injected by the lifespan in main.py
executor: Any = None


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check (no auth required)."""
    return {"status": "ok", "service": "trend-cultural-insights-agent", "version": "1.0.0"}


async def _execute_analysis(
    payload: ExecuteRequest,
    tenant_id: str,
) -> dict[str, Any]:
    """Shared execution logic for /v1/execute and /v1/trends."""
    if executor is None:
        return {"error": "Service not initialized", "findings": [], "sources": []}

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
    """Orchestrator dispatch endpoint."""
    return await _execute_analysis(payload, x_tenant_id)


@router.post("/v1/trends")
async def trends(
    payload: ExecuteRequest,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias for /v1/execute (backward compat)."""
    return await _execute_analysis(payload, x_tenant_id)
