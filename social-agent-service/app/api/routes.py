"""FastAPI route handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Header, HTTPException

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse

if TYPE_CHECKING:
    from app.services.social_executor import SocialExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

executor: Optional[SocialExecutor] = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.post("/v1/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    if executor is not None:
        return await executor.execute(request, x_tenant_id)

    logger.warning("Executor not initialised — returning stub response")
    return ExecuteResponse(
        findings=["Social agent received request (stub mode)"],
        recommendations=["Configure SOCIAL_GOOGLE_API_KEY for AI adaptation"],
    )
