"""
API routes for odoo-worker-agent-svc.

Endpoints:
  GET  /health       — Health check (no auth)
  POST /v1/execute   — Execute Odoo operations via persona-driven PAOR loop
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from app.services.executor import WorkerExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor — initialized in main.py lifespan
executor: Optional[WorkerExecutor] = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/v1/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """
    Execute Odoo operations via persona-driven PAOR loop.

    Accepts the same payload the orchestrator's ExternalWrapper sends.
    Resolves a business persona, loads relevant skills, and executes
    multi-step MCP tool calls through the PAOR reasoning loop.
    """
    if executor is not None:
        return await executor.execute(request, x_tenant_id)

    # Fallback stub when executor not initialized
    return ExecuteResponse(
        status="stub",
        findings=[f"Stub: Odoo worker pending for '{request.input_prompt[:80]}'."],
        recommendations=[
            "Deploy odoo-worker-agent-svc with Gemini API key for full functionality."
        ],
    )
