"""API routes for Odoo MCP Server."""

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Header, Request

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
)

if TYPE_CHECKING:
    from app.cache.redis_manager import RedisManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Set by the lifespan hook in main.py.
redis_manager: Optional["RedisManager"] = None
odoo_connected: bool = False


def _get_client_ip(http_request: Request) -> str:
    """Extract client IP from X-Forwarded-For or fallback to direct IP."""
    forwarded = http_request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(odoo_connected=odoo_connected)


@router.post("/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    http_request: Request,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """Execute an Odoo MCP operation.

    Receives X-Tenant-ID from orchestrator's ExternalWrapper.
    Extracts skill_context from config dict (same pattern as content-agent).
    """
    # Rate limit
    if redis_manager is not None:
        allowed = await redis_manager.check_rate_limit(x_tenant_id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
            )

    # Extract skill context (injected by orchestrator's SkillRouter)
    skill_context = request.config.get("skill_context", "")
    if skill_context:
        logger.info(
            "Received skill context for tenant %s (%d chars)",
            x_tenant_id,
            len(skill_context),
        )

    logger.info(
        "Execute request for tenant %s: %s",
        x_tenant_id,
        request.input_prompt[:100] if request.input_prompt else "(empty)",
    )

    return ExecuteResponse(
        status="success",
        findings=["Odoo MCP Server received the request"],
        recommendations=["Configure ODOO_URL for live Odoo connectivity"],
        data={
            "tenant_id": x_tenant_id,
            "prompt": request.input_prompt,
            "skill_context_length": len(skill_context),
        },
    )
