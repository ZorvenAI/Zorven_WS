"""
API routes for the pipeline orchestrator service.

Endpoints:
    GET  /health                    — Health check (no auth)
    POST /v1/jobs/dispatch          — Accept a job for execution
    POST /v1/jobs/{job_id}/cancel   — Cancel a running job
    POST /v1/admin/reload-skills    — Hot-reload skill files
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.auth import verify_service_token
from app.api.schemas import (
    CancelResponse,
    DispatchRequest,
    DispatchResponse,
    HealthResponse,
)
from app.core.redis_client import get_redis
from app.services.job_executor import JobExecutor

logger = logging.getLogger(__name__)

router = APIRouter()
executor = JobExecutor()

# Set by the lifespan hook in main.py.
skill_router: Optional["SkillRouter"] = None  # noqa: F821


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint — no authentication required."""
    return HealthResponse()


@router.post(
    "/v1/admin/reload-skills",
    dependencies=[Depends(verify_service_token)],
)
async def reload_skills(request: Request) -> dict:
    """Hot-reload skill files without restarting the service."""
    global skill_router

    from app.skills.loader import load_all_skills
    from app.skills.registry import SkillRegistry
    from app.skills.router import SkillRouter

    skills = load_all_skills()
    registry = SkillRegistry(skills)
    skill_router = SkillRouter(registry)

    logger.info("Skills reloaded: %d skill(s) available", skill_router.skill_count)
    return {"reloaded": True, "skill_count": skill_router.skill_count}


@router.post(
    "/v1/jobs/dispatch",
    status_code=202,
    response_model=DispatchResponse,
    dependencies=[Depends(verify_service_token)],
)
async def dispatch_job(
    request: DispatchRequest,
    background_tasks: BackgroundTasks,
) -> DispatchResponse:
    """
    Accept a pipeline job for execution.

    Returns 202 immediately and processes the job asynchronously.
    Progress and results are reported via HTTP callbacks to
    the callback_url provided in the request.
    """
    logger.info(
        "Job %s accepted for dispatch (manifest: %s)",
        request.job_id,
        "auto-detect" if request.manifest is None else "provided",
    )

    # Launch job execution in background
    background_tasks.add_task(executor.execute, request)

    return DispatchResponse()


@router.post(
    "/v1/jobs/{job_id}/cancel",
    response_model=CancelResponse,
    dependencies=[Depends(verify_service_token)],
)
async def cancel_job(job_id: str) -> CancelResponse:
    """
    Cancel a running or queued job.

    Sets a cancel flag in Redis that the job executor checks
    between node executions.
    """
    redis = await get_redis()
    await redis.set(f"cancel:{job_id}", "1", ex=3600)
    logger.info("Cancel flag set for job %s", job_id)
    return CancelResponse()
