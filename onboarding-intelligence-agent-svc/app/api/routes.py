"""HTTP routes.

A-05 delivered the health surface. C-01 adds ``/v1/execute`` — the PREP
envelope from §10.2.1 that C-02 through C-04 all ride. ``/v1/onboarding``,
``/v1/process`` and ``/v1/process/{job_id}`` arrive with their own stories.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.logic.process_executor import ProcessExecutor

from app.core.logging import get_logger

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import verify_service_token
from app.api.schemas import (
    CacheBustRequest,
    CacheBustResponse,
    DLQReplayRequest,
    DLQReplayResponse,
    ErasureRequest,
    ErasureResponse,
    ExecuteRequest,
    ExecuteResponse,
    GuardrailReport,
    ProcessRequest,
    ProcessResponse,
    SkillExecuteRequest,
    UsageReport,
)
from app.cache.conversation import ConversationStore
from app.logic.rate_limiter import check_rate
from app.logic.prep_executor import QUESTIONNAIRE_SKILL, RESEARCH_SKILL
from app.skills.models import Origin, SkillContext, TenantContext
from app.skills.questionnaire_models import GeneratedQuestionnaire
from app.skills.research_brief import BusinessResearchBrief

logger = get_logger(__name__)

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
async def health() -> dict[str, Any]:
    """Liveness probe (Design §20, M-04 AC-1). Static OK — no dependency checks.

    Readiness is the place where dependency state is reported. A liveness
    probe that contacts external systems causes Cloud Run to restart the
    container when a dependency is temporarily down, which worsens the
    outage rather than recovering from it.
    """
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
    """Readiness probe (Design §20, M-04 AC-1, NFR-OPS-01).

    Probes Redis, Kafka (when configured), and the STT credential path.
    A rolling deploy cannot route traffic to an instance that will fail
    on first use.
    """
    import os

    deps = await _dependency_status(request)
    settings = request.app.state.settings

    stt = getattr(request.app.state, "stt", None)
    stt_configured = stt is not None and getattr(stt, "configured", False)
    stt_creds_ok = True
    if settings.STT_CREDENTIALS:
        stt_creds_ok = os.access(settings.STT_CREDENTIALS, os.R_OK)

    breakers = getattr(request.app.state, "breakers", None)
    stt_breaker = breakers.get("stt") if breakers is not None else None
    stt_breaker_state = (
        stt_breaker.state.value if stt_breaker is not None else "unknown"
    )

    deps["stt"] = {
        "required": True,
        "healthy": stt_configured and stt_creds_ok,
        "configured": stt_configured,
        "credentials_readable": stt_creds_ok,
        "breaker_state": stt_breaker_state,
        "detail": (
            "configured and credentials readable"
            if stt_configured and stt_creds_ok
            else (
                "credentials file not readable"
                if stt_configured
                else "not configured — set OIA_STT_PROJECT"
            )
        ),
    }

    failed = [
        name
        for name, state in deps.items()
        if state["required"] and not state["healthy"]
    ]

    degraded = [
        name
        for name, state in deps.items()
        if not state["required"]
        and state.get("breaker_state") == "OPEN"
        or (name == "stt" and stt_breaker_state == "OPEN" and name not in failed)
    ]

    if failed:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "service": SERVICE_NAME,
            "failed": failed,
            "dependencies": deps,
        }

    if degraded:
        return {
            "status": "degraded",
            "service": SERVICE_NAME,
            "degraded": degraded,
            "dependencies": deps,
        }

    return {"status": "ready", "service": SERVICE_NAME, "dependencies": deps}


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
    user_id = payload.tenant_context.user_id or "anonymous"
    settings = request.app.state.settings

    redis = request.app.state.redis
    rl_key = redis.keys_for(tenant_id).ratelimit(user_id)
    rl_count, rl_exceeded = await check_rate(
        redis.client, rl_key, settings.RATE_LIMIT_PREP_PER_MIN
    )
    if rl_exceeded:
        events = getattr(request.app.state, "events", None)
        if events is not None:
            from app.events.catalog import EventType

            try:
                await events.emit(
                    EventType.AGENT_RATE_LIMITED,
                    tenant_id=tenant_id,
                    correlation_id=(
                        payload.tenant_context.correlation_id
                        or payload.tenant_context.trace_id
                    ),
                    session_id=payload.session_id or "",
                    payload={
                        "user_id": user_id,
                        "count": rl_count,
                        "limit": settings.RATE_LIMIT_PREP_PER_MIN,
                    },
                    outcome="BLOCKED",
                )
            except Exception:  # noqa: BLE001
                pass
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Rate limit exceeded: {rl_count}/"
                f"{settings.RATE_LIMIT_PREP_PER_MIN} per minute"
            ),
        )

    store = ConversationStore(redis)
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

    # L-01: resolve and pin prompt versions at session start.
    from app.prompts.mapping import PREP_PROMPTS

    prompt_versions: dict[str, str] = {}
    loader = getattr(request.app.state, "prompt_loader", None)
    if loader is not None:
        resolved, degraded = await loader.resolve_for_session(PREP_PROMPTS, tenant_id)
        prompt_versions = {pid: r.version for pid, r in resolved.items()}
        if payload.session_id:
            import json as _json

            keys = request.app.state.redis.keys_for(tenant_id)
            await request.app.state.redis.client.hset(
                keys.session(payload.session_id),
                "prompt_versions",
                _json.dumps(prompt_versions),
            )
        if degraded:
            events = getattr(request.app.state, "events", None)
            if events is not None:
                from app.events.catalog import EventType

                try:
                    await events.emit(
                        EventType.AGENT_INVOKED,
                        tenant_id=tenant_id,
                        correlation_id=(
                            payload.tenant_context.correlation_id
                            or payload.tenant_context.trace_id
                        ),
                        session_id=payload.session_id or "",
                        payload={"prompt_source": "hardcoded_fallback"},
                        outcome="DEGRADED",
                    )
                except Exception:  # noqa: BLE001
                    pass

    rl_config = {
        "_ig07_count": rl_count,
        "_rate_limit": settings.RATE_LIMIT_PREP_PER_MIN,
    }
    brief, from_cache = await request.app.state.prep.research(
        tenant=tenant,
        input_context=payload.input_context,
        input_prompt=payload.input_prompt,
        correlation_id=payload.tenant_context.correlation_id or "",
        config=rl_config,
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
            config=rl_config,
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
        prompt_version=prompt_versions,
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


@router.post(
    "/v1/execute/skill",
    response_model=ExecuteResponse,
    dependencies=[Depends(verify_service_token)],
)
async def execute_skill(
    request: Request, payload: SkillExecuteRequest
) -> ExecuteResponse:
    """Direct skill invocation for backend-triggered skills (I-02).

    Unlike ``/v1/execute`` this does not carry conversation state or run the
    PREP orchestrator. It dispatches a single skill through the registry's
    full guardrail chain (IG → RBAC → PG → skill → OG) and returns the
    result. Used by Django's Celery task to trigger SKL-OIA-08 after a
    recording stops.
    """
    started = time.monotonic()

    tenant = TenantContext(
        tenant_id=payload.tenant_context.tenant_id,
        user_id=payload.tenant_context.user_id,
        role=payload.tenant_context.role,
    )
    context = SkillContext(
        input_prompt="",
        tenant_context=tenant,
        input_context=payload.input_context,
        config=payload.config,
        correlation_id=payload.tenant_context.correlation_id or "",
        origin=Origin.INTERNAL,
    )

    registry = request.app.state.skill_registry
    try:
        result = await registry.execute(payload.skill_id, context)
    except NotImplementedError:
        return ExecuteResponse(
            status="FAILED",
            skill_id=payload.skill_id,
            output={"error": f"Skill {payload.skill_id} is not yet implemented"},
            usage=UsageReport(duration_ms=int((time.monotonic() - started) * 1000)),
        )
    except Exception as exc:
        logger.error("skill_execute_failed", skill_id=payload.skill_id, error=str(exc))
        return ExecuteResponse(
            status="FAILED",
            skill_id=payload.skill_id,
            output={"error": f"{type(exc).__name__}: skill execution failed"},
            usage=UsageReport(duration_ms=int((time.monotonic() - started) * 1000)),
        )

    return ExecuteResponse(
        status="SUCCEEDED",
        skill_id=result.skill_id,
        output=result.output,
        usage=UsageReport(
            duration_ms=result.duration_ms or int((time.monotonic() - started) * 1000)
        ),
    )


@router.post(
    "/v1/process",
    response_model=ProcessResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_service_token)],
)
async def process(
    request: Request,
    payload: ProcessRequest,
) -> ProcessResponse:
    """Accept a PROCESS job (J-01, §10.2.2).

    Validates the manifest, checks idempotency, spawns a background task
    and returns 202 immediately. The actual extraction logic (J-02)
    runs asynchronously and calls back to Django on completion.
    """
    idempotency_key = request.headers.get("idempotency-key", "")
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    executor: ProcessExecutor = request.app.state.process_executor

    tenant_ctx = TenantContext(
        tenant_id=payload.tenant_context.tenant_id,
        user_id=payload.tenant_context.user_id,
        role=payload.tenant_context.role,
        session_id=payload.session_id,
    )

    return await executor.accept(
        tenant=tenant_ctx,
        session_id=payload.session_id,
        manifest=payload.evidence_manifest,
        options=payload.options,
        callback_url=payload.callback_url,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/v1/admin/cache-bust",
    response_model=CacheBustResponse,
    dependencies=[Depends(verify_service_token)],
)
async def cache_bust(
    request: Request,
    payload: CacheBustRequest,
) -> CacheBustResponse:
    """Bust prompt cache for incident recovery (L-05, §20).

    Clears POI's Redis cache (``prompt:zorven-oia-*``) and OIA's
    write-through cache (``oia:v1:{tenant}:prompt_cache:*``) so the
    resolution chain falls through to the POI API and picks up the
    reverted version. In-flight sessions are unaffected — their prompt
    versions are pinned in the session hash.
    """
    loader = getattr(request.app.state, "prompt_loader", None)
    if loader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prompt loader not initialized",
        )

    prompt_ids = [payload.prompt_id] if payload.prompt_id else None
    cleared = await loader.bust_cache(
        prompt_ids=prompt_ids,
        tenant_id=payload.tenant_id,
    )

    from app.prompts.mapping import ALL_PROMPT_IDS

    return CacheBustResponse(
        cleared=cleared,
        prompt_ids=[payload.prompt_id] if payload.prompt_id else list(ALL_PROMPT_IDS),
        tenant_id=payload.tenant_id,
    )


# ── N-03: DLQ replay ─────────────────────────────────────────


@router.post(
    "/v1/admin/dlq/replay",
    response_model=DLQReplayResponse,
    dependencies=[Depends(verify_service_token)],
)
async def replay_dlq(
    request: Request,
    payload: DLQReplayRequest,
) -> DLQReplayResponse:
    """Replay dead-lettered commands (N-03, §20).

    Re-publishes each DLQ message to its original topic with the same
    idempotency_key.  Messages that have already failed ≥ 3 replay
    attempts are archived to the poison-message topic instead.
    """
    from app.messaging.dlq_replay import replay_batch

    kafka = request.app.state.kafka
    if kafka is None or not getattr(kafka, "configured", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer not configured",
        )
    if not getattr(kafka, "started", False):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kafka producer not started",
        )

    settings = request.app.state.settings
    summary = await replay_batch(
        kafka,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        batch_size=payload.batch_size,
    )
    return DLQReplayResponse(
        replayed=summary.replayed,
        archived=summary.archived,
        errors=summary.errors,
        details=summary.details,
    )


# ── M-02: GDPR erasure ────────────────────────────────────────


@router.delete(
    "/v1/admin/erasure",
    response_model=ErasureResponse,
    dependencies=[Depends(verify_service_token)],
    status_code=status.HTTP_200_OK,
)
async def erasure(request: Request, payload: ErasureRequest) -> ErasureResponse:
    """Delete all session-scoped Redis keys for the given sessions.

    Called by Django's GDPR erasure cascade. Iterates every key builder
    on TenantKeys for each session_id, then falls back to a SCAN for
    any keys the explicit list missed.
    """
    from app.cache.redis_manager import KEY_PREFIX, TenantKeys

    redis = request.app.state.redis.client
    keys = TenantKeys(payload.tenant_id)

    deleted_keys: set[str] = set()

    for sid in payload.session_ids:
        session_keys = [
            keys.session(sid),
            keys.session_summary(sid),
            keys.transcript(sid),
            keys.questions(sid),
            keys.coverage(sid),
            keys.live_frames(sid),
            keys.unmapped(sid),
            keys.live_seq(sid),
            keys.outbox(sid),
        ]
        for key in session_keys:
            try:
                removed = await redis.delete(key)
                if removed:
                    deleted_keys.add(key)
            except Exception:
                logger.warning("erasure_key_delete_failed", key=key)

    scan_prefix = f"{KEY_PREFIX}{payload.tenant_id}:"
    for sid in payload.session_ids:
        pattern = f"{scan_prefix}*:{sid}:*"
        cursor: int | str = 0
        while True:
            cursor, found = await redis.scan(cursor=cursor, match=pattern, count=100)
            for key in found:
                if key not in deleted_keys:
                    try:
                        await redis.delete(key)
                        deleted_keys.add(key)
                    except Exception:
                        logger.warning("erasure_scan_delete_failed", key=key)
            if cursor == 0:
                break

    result_keys = sorted(deleted_keys)
    return ErasureResponse(
        deleted_keys=result_keys,
        total=len(result_keys),
    )
