"""API routes for Odoo MCP Server."""

import logging
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, HTTPException, Header, Request

from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    ToolCallRequest,
    ToolCallResponse,
)
from app.core.config import settings

if TYPE_CHECKING:
    from app.cache.redis_manager import RedisManager
    from app.services.connection_pool import TenantConnectionPool
    from app.tenancy.registry import TenantRegistry
    from app.tools.dispatcher import ToolDispatcher

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_service_token(token: str) -> None:
    """Verify X-Service-Token for internal endpoints."""
    if token != settings.SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid service token")


# Set by the lifespan hook in main.py.
redis_manager: Optional["RedisManager"] = None
rag_client: Optional[object] = None
tool_dispatcher: Optional["ToolDispatcher"] = None
connection_pool: Optional["TenantConnectionPool"] = None
tenant_registry: Optional["TenantRegistry"] = None
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


async def _get_rpc_client(tenant_id: str) -> Any:
    """Resolve tenant config and return an authenticated OdooRPCClient."""
    if connection_pool is None or tenant_registry is None:
        raise HTTPException(status_code=503, detail="Tool dispatch not initialized")
    config = await tenant_registry.get_config(tenant_id)
    return await connection_pool.get_client(
        tenant_id=tenant_id,
        url=config.odoo_url,
        db=config.odoo_db,
        username=config.odoo_username,
        password=config.odoo_password,
    )


@router.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(
    request: ToolCallRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    x_service_token: str = Header(alias="X-Service-Token"),
) -> ToolCallResponse:
    """Execute an MCP tool by name with tenant-scoped Odoo connection."""
    _verify_service_token(x_service_token)
    if tool_dispatcher is None:
        raise HTTPException(status_code=503, detail="Tool dispatcher not initialized")

    tenant_id = request.tenant_id or x_tenant_id

    # Get an authenticated Odoo RPC client for this tenant
    try:
        rpc_client = await _get_rpc_client(tenant_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get RPC client for tenant %s: %s", tenant_id, exc)
        return ToolCallResponse(
            tool_name=request.tool_name,
            success=False,
            error=f"Odoo connection failed: {exc}",
        )

    context = {
        "rpc_client": rpc_client,
        "tenant_id": tenant_id,
    }

    logger.info(
        "Tool call: %s (tenant=%s, args=%s)",
        request.tool_name,
        tenant_id,
        list(request.arguments.keys()),
    )

    result = await tool_dispatcher.dispatch(
        tool_name=request.tool_name,
        arguments=request.arguments,
        context=context,
    )

    return ToolCallResponse(
        tool_name=request.tool_name,
        success=result.get("success", False),
        result=result.get("result"),
        error=result.get("error"),
        duration_ms=result.get("duration_ms"),
    )


@router.get("/tools")
async def list_tools(
    domain: Optional[str] = None,
    x_service_token: str = Header(alias="X-Service-Token"),
) -> dict[str, Any]:
    """List available MCP tools, optionally filtered by domain."""
    _verify_service_token(x_service_token)
    if tool_dispatcher is None:
        return {"tools": [], "count": 0}

    tools = tool_dispatcher.registry.list_tools(domain=domain)
    return {"tools": tools, "count": len(tools)}
