"""API endpoints for the Audience Persona Agent service."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.auth import verify_service_token
from app.api.schemas import AudiencePersonaResponse, ExecuteRequest
from app.core.config import settings
from app.services.apa_executor import APAExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level executor, injected from main.py lifespan
executor: APAExecutor | None = None


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint (no auth required)."""
    return {"status": "ok", "service": "audience-persona-agent"}


@router.get("/health/diagnostics")
async def diagnostics() -> dict:
    """Detailed diagnostics — helps debug stub mode / low confidence in deployed environments."""
    api_key = settings.ANTHROPIC_API_KEY
    tavily_key = settings.TAVILY_API_KEY

    has_anthropic = bool(api_key and len(api_key) > 8)
    has_tavily = bool(tavily_key and len(tavily_key) > 4)

    issues: list[str] = []
    if not has_anthropic:
        issues.append(
            "APA_ANTHROPIC_API_KEY is missing — running in STUB MODE"
        )
    if not has_tavily:
        issues.append(
            "APA_TAVILY_API_KEY is missing — web search disabled"
        )

    return {
        "service": "audience-persona-agent",
        "mode": "LIVE" if has_anthropic else "STUB",
        "model": settings.LLM_MODEL,
        "keys_configured": {
            "APA_ANTHROPIC_API_KEY": has_anthropic,
            "APA_TAVILY_API_KEY": has_tavily,
        },
        "issues": issues,
        "executor_initialized": executor is not None,
    }


async def _execute_analysis(
    payload: ExecuteRequest,
    tenant_id: str,
) -> dict[str, Any]:
    """Shared execution logic for /v1/execute and /v1/personas."""
    if executor is None:
        logger.warning("Executor not initialized, returning stub response")
        return AudiencePersonaResponse(
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
    """Execute audience persona analysis (orchestrator dispatch endpoint)."""
    logger.info(
        "Execute request: tenant=%s, prompt=%.80s",
        x_tenant_id,
        payload.input_prompt,
    )
    return await _execute_analysis(payload, x_tenant_id)


@router.post("/v1/personas")
async def personas(
    payload: ExecuteRequest,
    _token: str = Depends(verify_service_token),
    x_tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
) -> dict[str, Any]:
    """Alias endpoint for persona generation."""
    logger.info(
        "Persona request: tenant=%s, prompt=%.80s",
        x_tenant_id,
        payload.input_prompt,
    )
    return await _execute_analysis(payload, x_tenant_id)
