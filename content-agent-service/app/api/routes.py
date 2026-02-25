"""
API routes for content-agent-svc.

Endpoints:
  GET  /health       — Health check (no auth)
  POST /v1/execute   — Execute blog authoring (primary endpoint)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Header

from app.api.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from app.services.content_executor import ContentExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor — initialized in main.py lifespan
executor: Optional[ContentExecutor] = None


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
    Execute blog authoring with SEO/AEO/GEO optimization.

    Accepts the same payload the orchestrator's ExternalWrapper sends.
    """
    if executor is not None:
        return await executor.execute(request, x_tenant_id)

    # Fallback stub when executor not initialized
    return ExecuteResponse(
        findings=[
            f"Stub finding: Blog authoring pending for '{request.input_prompt[:50]}'."
        ],
        recommendations=[
            "Deploy content-agent-svc with Gemini API key for real blog generation."
        ],
        blog_content=f"# {request.input_prompt}\n\nStub blog content. "
        "Configure the content agent service for full functionality.",
        word_count=10,
    )
