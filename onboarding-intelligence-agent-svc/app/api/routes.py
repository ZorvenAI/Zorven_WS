"""HTTP routes.

A-05 delivers the health surface only. ``/v1/execute``, ``/v1/onboarding``,
``/v1/process`` and ``/v1/process/{job_id}`` are declared in Design §4.2 and
arrive with the stories that implement PREP and PROCESS.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

router = APIRouter()

SERVICE_NAME = "onboarding-intelligence-agent"


async def _dependency_status(request: Request) -> dict[str, dict[str, Any]]:
    """Probe every dependency and describe what it actually reports."""
    redis_manager = request.app.state.redis
    kafka = request.app.state.kafka
    settings = request.app.state.settings

    redis_ok = await redis_manager.ping()
    kafka_live = await kafka.is_live()

    return {
        "redis": {
            "required": True,
            "healthy": redis_ok,
            "db": settings.REDIS_DB,
            "detail": (
                f"DB {settings.REDIS_DB}, key prefix oia:v1: "
                "(shared instance — ERRATA-01)"
            ),
        },
        "kafka": {
            # Kafka is a hard requirement only where a broker exists. No
            # deployment/gcp script provisions one, so in production this is
            # reported and not enforced.
            "required": kafka.configured,
            "healthy": kafka_live,
            "configured": kafka.configured,
            "detail": (
                "broker reachable"
                if kafka.configured and kafka_live
                else (
                    "configured but unreachable"
                    if kafka.configured
                    else "not configured — event emission disabled"
                )
            ),
        },
        "backend": {
            "required": False,
            "healthy": bool(settings.BACKEND_BASE_URL),
            "detail": settings.BACKEND_BASE_URL or "unset",
        },
        "poi": {
            "required": False,
            "healthy": bool(settings.POI_TOKEN),
            "detail": (
                f"prompt cache DB {settings.POI_PROMPT_CACHE_DB}, "
                "read-only under poi:"
            ),
        },
        "gcs": {
            "required": False,
            "healthy": bool(settings.GCS_BUCKET),
            "detail": settings.GCS_BUCKET or "unset",
        },
    }


@router.get("/health")
async def health(request: Request, response: Response) -> dict[str, Any]:
    """Liveness probe that actually checks its dependencies.

    Returns 200 only when every **required** dependency answers. Redis is
    always required; Kafka is required only where a broker is configured.
    Both underlying checks are bounded by 2 s socket timeouts, so this
    answers within the AC-3 budget rather than hanging.
    """
    deps = await _dependency_status(request)
    failed = [
        name
        for name, state in deps.items()
        if state["required"] and not state["healthy"]
    ]

    if failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "service": SERVICE_NAME,
            "failed": failed,
        }

    return {"status": "ok", "service": SERVICE_NAME}


@router.get("/health/diagnostics")
async def diagnostics(request: Request) -> dict[str, Any]:
    """Per-dependency detail, including dependencies /health does not gate on."""
    settings = request.app.state.settings
    deps = await _dependency_status(request)

    return {
        "service": SERVICE_NAME,
        "port": settings.PORT,
        "env_prefix": "OIA_",
        "redis_db": settings.REDIS_DB,
        "prompt_cache_db": settings.POI_PROMPT_CACHE_DB,
        "key_prefix": "oia:v1:",
        "dependencies": deps,
        "settings": {
            "sufficiency_green_threshold": settings.SUFFICIENCY_GREEN_THRESHOLD,
            "live_analysis_silence_ms": settings.LIVE_ANALYSIS_SILENCE_MS,
            "transcript_buffer_max": settings.TRANSCRIPT_BUFFER_MAX,
            "context_summarize_at": settings.CONTEXT_SUMMARIZE_AT,
            "retention_days_default": settings.RETENTION_DAYS_DEFAULT,
            "stt_language_default": settings.STT_LANGUAGE_DEFAULT,
            "max_concurrent_live_per_company": (
                settings.MAX_CONCURRENT_LIVE_PER_COMPANY
            ),
            "process_timeout_s": settings.PROCESS_TIMEOUT_S,
        },
        "secrets_configured": {
            "OIA_STT_CREDENTIALS": bool(settings.STT_CREDENTIALS),
            "OIA_GEMINI_KEY": bool(settings.GEMINI_KEY),
            "OIA_SERVICE_TOKEN": bool(settings.SERVICE_TOKEN),
            "OIA_POI_TOKEN": bool(settings.POI_TOKEN),
        },
    }
