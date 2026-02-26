"""HTTP endpoints for the RAG uploader agent service."""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# Set by lifespan in main.py
executor: Optional["UploaderExecutor"] = None  # noqa: F821


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/v1/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> ExecuteResponse:
    """Execute the RAG upload workflow.

    Receives pipeline context from the orchestrator's ExternalWrapper
    and archives files to the permanent knowledge base.
    """
    logger.info(
        "POST /v1/execute — tenant=%s, prompt='%s', "
        "input_context keys=%s, previous_outputs keys=%s",
        x_tenant_id,
        request.input_prompt[:80],
        list(request.input_context.keys()),
        list(request.previous_outputs.keys()),
    )
    if executor is not None:
        return await executor.execute(request, x_tenant_id)

    # Stub fallback when executor not initialized
    return ExecuteResponse(
        findings=["RAG uploader service not fully initialized."],
        recommendations=["Check service logs for configuration issues."],
    )
