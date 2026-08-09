"""HTTP routes.

A-05 delivered the health surface. C-01 adds ``/v1/execute`` — the PREP
envelope from §10.2.1 that C-02 through C-04 all ride. ``/v1/onboarding``,
``/v1/process`` and ``/v1/process/{job_id}`` arrive with their own stories.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import verify_service_token
from app.api.schemas import (
    ExecuteRequest,
    ExecuteResponse,
    GuardrailReport,
    UsageReport,
)
from app.cache.conversation import ConversationStore
from app.logic.prep_executor import QUESTIONNAIRE_SKILL, RESEARCH_SKILL
from app.skills.models import TenantContext
from app.skills.questionnaire_models import GeneratedQuestionnaire
from app.skills.research_brief import BusinessResearchBrief

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


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, Any]:
    """Readiness probe (Design §20).

    §20 describes /health as liveness only and /ready as the probe that
    checks dependencies, while A-05's AC-3 required /health to check them.
    Both readings are honoured: /health keeps the behaviour A-05 shipped and
    is tested, and /ready is the §20-named endpoint with the same semantics,
    so a rolling deploy can point at either name.
    """
    deps = await _dependency_status(request)
    failed = [
        name
        for name, state in deps.items()
        if state["required"] and not state["healthy"]
    ]
    if failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "service": SERVICE_NAME, "failed": failed}
    return {"status": "ready", "service": SERVICE_NAME}


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    """Prometheus exposition (Design §20)."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.post(
    "/v1/execute",
    response_model=ExecuteResponse,
    dependencies=[Depends(verify_service_token)],
)
async def execute(request: Request, payload: ExecuteRequest) -> ExecuteResponse:
    """A PREP turn (§10.2.1, §2.1).

    C-01 delivers the envelope, the auth and the conversation state. It does
    not yet run a skill: SKL-OIA-01 and 02 are C-02 and C-03, and the registry
    has no PREP skill registered to call. So the turn is recorded, the history
    is returned, and ``skill_id`` says plainly that none ran.

    Returning a truthful empty result beats either faking one or 501-ing: C-02
    needs this envelope to exist to build against, and Django needs to be able
    to route a turn end to end before there is anything to say back.
    """
    started = time.monotonic()
    tenant_id = payload.tenant_context.tenant_id

    store = ConversationStore(request.app.state.redis)
    await store.append(
        tenant_id=tenant_id,
        chat_session_id=payload.chat_session_id,
        role="operator",
        text=payload.input_prompt,
    )
    history = await store.history(
        tenant_id=tenant_id, chat_session_id=payload.chat_session_id
    )

    tenant = TenantContext(
        tenant_id=tenant_id,
        user_id=payload.tenant_context.user_id,
        role=payload.tenant_context.role,
        session_id=payload.session_id,
    )

    brief, from_cache = await request.app.state.prep.research(
        tenant=tenant,
        input_context=payload.input_context,
        input_prompt=payload.input_prompt,
        correlation_id=payload.tenant_context.correlation_id or "",
    )

    summary = BusinessResearchBrief.model_validate(brief).summary_line()

    # C-03. A turn asking for questions gets them in the same turn as the
    # research they are built from — the operator asked once, and making them
    # ask again after seeing a brief would be a worse conversation.
    #
    # `count` is the trigger. Intent detection lives in Django (C-01's
    # classifier); by the time a turn reaches here the caller has already
    # decided this is preparation, and the presence of a requested count is
    # what distinguishes "research this" from "research it and draft me
    # twelve questions".
    generated: dict[str, Any] | None = None
    stored: dict[str, Any] | None = None
    if payload.input_context.get("count") is not None:
        generated, stored = await request.app.state.prep.generate_questionnaire(
            tenant=tenant,
            brief=brief,
            count=payload.input_context.get("count"),
            depth=payload.input_context.get("depth", "standard"),
            input_prompt=payload.input_prompt,
            chat_session_id=payload.chat_session_id,
            correlation_id=payload.tenant_context.correlation_id or "",
        )
        questionnaire = GeneratedQuestionnaire.model_validate(generated)
        # The questionnaire's summary replaces the brief's: it is the answer to
        # what the operator asked, and it already names the coverage gaps AC-3
        # wants them to act on before approving.
        summary = questionnaire.summary_line()
        if questionnaire.questions and stored is None:
            # AC-4 says a DRAFT row exists. Telling an operator "12 questions
            # ready" when nothing was saved would send them looking for an
            # approval screen with nothing on it.
            summary += " (not saved — the questions are above but could not be stored.)"

    # The brief is recorded as an agent turn so the next turn sees it. C-01
    # built the history for exactly this — an operator saying "go deeper on
    # their supply chain" needs the agent to know what it already found.
    await store.append(
        tenant_id=tenant_id,
        chat_session_id=payload.chat_session_id,
        role="agent",
        text=summary,
    )

    return ExecuteResponse(
        status="SUCCEEDED",
        skill_id=QUESTIONNAIRE_SKILL if generated else RESEARCH_SKILL,
        output={
            "turns": len(history),
            "history": history,
            # `detail` is what the operator actually reads: Django's dispatcher
            # renders output.detail into the chat bubble and falls back to
            # "Preparation is under way." when it is absent. Dropping this key
            # would replace every prep reply with that placeholder, and no test
            # on this side would have noticed.
            "detail": summary,
            "research_brief": brief,
            "from_cache": from_cache,
            "questionnaire": generated,
            "stored_questionnaire_id": (stored or {}).get("id"),
        },
        guardrails=GuardrailReport(
            # OG-01 demotes rather than blocks, so a brief that lost facts
            # still passes — the demotion is visible in open_unknowns, and
            # reporting FAIL would tell an operator the turn failed when it
            # did exactly what it should.
            output="PASS",
        ),
        usage=UsageReport(duration_ms=int((time.monotonic() - started) * 1000)),
    )
