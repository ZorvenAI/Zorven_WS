"""WebSocket endpoint for LIVE mode — WS /v1/live/{session_id}.

Design §10.2.3, §4.3 · **the IG-10 gate only** (C-04 AC-4). The live protocol —
audio in, partial transcripts and signals out, reconnect and replay — is F-04.

Scaffolded by A-05, which named F-04 as the implementer. C-04 AC-4 needs the
refusal before F-04 needs the protocol: "a live session is attempted, it is
refused — the IG-10 gate — closing with 4403 and a message naming the missing
approval". Building only the gate keeps that AC honest without pre-empting the
streaming design.

**Read `docs/spikes/A-02-gateway-websocket-note.md` before extending this.**
Three findings from that spike shape what is here:

1. A close code cannot be delivered before ``accept()``. Closing a Starlette
   socket pre-accept makes the framework answer the handshake with plain HTTP
   403 and the client never sees a code. So the decision is made before accept
   and only the *verdict* is delivered after it — accept, then immediately
   close. No frame is ever read from or written to a refused socket.
2. The token arrives as ``?jwt=``: browsers cannot set headers on a WebSocket
   handshake. It therefore appears in gateway logs and browser history, so the
   frontend should mint a short-lived, single-purpose token rather than reuse
   the session JWT.
3. The rejection shape differs by environment — HTTP 401 before the upgrade
   through Kong, close 4401 after it on Cloud Run. A client must treat both as
   the same condition.

F-04 owns everything past the gate, including reading the tenant from a
verified claim. This endpoint takes the tenant from the query string, which is
adequate for a refusal that reveals nothing and is **not** adequate for a
socket that carries data — see the note on ``_tenant_of``.

F-05 adds the audio pipeline: binary audio → STT → partial/final frames.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.api.schemas import (
    ClientFrameType,
    ErrorFrame,
    EvidenceSpan,
    GreenSignal,
    MarkQuestionFrame,
    RecoveryFrame,
    ResumeFrame,
    StartFrame,
    TranscriptFinal,
    TranscriptPartial,
)
from app.circuit_breaker.breaker import (
    BreakerRegistry,
    CircuitBreakerOpen,
    State,
)
from app.events.catalog import EventType
from app.core.logging import get_logger
from app.logic.consent_gate import (
    ConsentState,
    consent_verdict,
    emit_refusal,
    fetch_consent_state,
)
from app.logic.live_handshake import (
    CLOSE_CONFLICT,
    CLOSE_FORBIDDEN,
    CLOSE_INTERNAL,
    CLOSE_UNAUTHORIZED,
    Handshake,
    evaluate,
    expired,
)
from app.logic.live_lock import REFRESH_S, LiveLock, acquire
from app.logic.live_session import LiveSessionManager, SegmentBatcher, SegmentBatch
from app.providers.stt import STTAdapter, STTResult, STTUnavailable
from app.skills.models import SkillContext, TenantContext, Origin
from app.skills.redact_pii import redact_text, RedactionResult
from app.skills.registry import SkillRegistry

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/v1/live/{session_id}")
async def live_websocket(websocket: WebSocket, session_id: str) -> None:
    """Authenticate, authorise, admit one socket, and hold it (F-04 PR 1).

    Everything AC-1 lists happens before ``accept()`` — spike A-02's first
    finding is that a close made any earlier reaches the client as plain HTTP
    403 with no code at all, so the decision is made first and only the
    *verdict* is delivered after accepting.

    The socket is then held open. C-04 closed it immediately on the grounds
    that "holding an accepted socket open with nothing behind it would look
    like a working meeting" — true when this file was only a gate. Holding the
    connection *is* the lifecycle, which is what this story owns; the frames
    that travel over it arrive in PR 2.
    """
    ticket = str(websocket.query_params.get("ticket") or "").strip()
    backend = getattr(websocket.app.state, "backend", None)
    events = getattr(websocket.app.state, "events", None)
    redis_manager = getattr(websocket.app.state, "redis", None)

    # The tenant now comes from the ticket Django resolved, not from a query
    # parameter the caller chose. C-04 flagged that as adequate for a refusal
    # and "**not** adequate for a socket that carries data" — this is that
    # socket, so it is fixed here.
    precheck = None
    if backend is not None:
        try:
            precheck = await backend.live_precheck(
                # Tenant is unknown until the ticket resolves, and the header
                # is what routes the request in Django. The ticket names the
                # tenant it belongs to, so a caller cannot widen its own scope
                # by naming another here — the auth block is authoritative.
                tenant_id=str(websocket.query_params.get("tenant_id") or ""),
                session_id=session_id,
                ticket=ticket,
            )
        except Exception:  # noqa: BLE001 - any failure is a refusal
            precheck = None

    verdict = evaluate(precheck)

    lock = None
    if not verdict.refused:
        lock = await acquire(
            redis_manager,
            tenant_id=verdict.tenant_id,
            company_id=verdict.company_id,
            token=uuid.uuid4().hex,
        )
        if lock is None:
            verdict = Handshake(
                code=CLOSE_CONFLICT,
                reason="Another socket is already live for this session.",
            )

    if verdict.refused:
        if verdict.code == CLOSE_FORBIDDEN and "consent" in verdict.reason:
            await emit_refusal(
                events,
                consent_verdict(ConsentState(present=False, active=False)),
                tenant_id=verdict.tenant_id or "unknown",
                session_id=session_id,
            )
        await websocket.accept()
        await websocket.close(
            code=verdict.code or CLOSE_INTERNAL, reason=verdict.reason
        )
        return

    await websocket.accept()
    try:
        await _hold(websocket, verdict, lock, backend, session_id, ticket, precheck)
    finally:
        if lock is not None:
            await lock.release()


async def _audio_from_queue(
    audio_q: asyncio.Queue[bytes | None],
) -> AsyncIterator[bytes]:
    """Adapt a Queue to the async iterator the STT adapter expects."""
    while True:
        chunk = await audio_q.get()
        if chunk is None:
            return
        yield chunk


async def _stt_loop(
    websocket: WebSocket,
    session: LiveSessionManager,
    stt: STTAdapter,
    audio_q: asyncio.Queue[bytes | None],
    *,
    codec: str,
    sample_rate: int,
    stt_state: dict[str, Any],
) -> None:
    """Background task: feed audio to STT, emit frames.

    Partials go to the client as-is — no LLM, no redaction (§4.3).
    Finals are redacted before buffering (IG-04/SKL-OIA-16) but sent
    unredacted to the client who is hearing the conversation live.

    When STT becomes unavailable (circuit breaker opens), this task sets
    the session mode to RECORD_ONLY, sends ERR-07, and spawns a recovery
    task that periodically probes STT (F-06 §18.2).
    """
    recording_id = str(stt_state.get("recording_id") or "")
    allowlist = stt_state.get("allowlist") or []
    batcher = stt_state.get("batcher")
    analysis_state = stt_state.get("analysis_state")
    try:
        async for result in stt.stream(
            _audio_from_queue(audio_q),
            sample_rate=sample_rate,
            codec=codec,
        ):
            if result.is_final:
                await _emit_final(
                    websocket,
                    session,
                    result,
                    recording_id=recording_id,
                    allowlist=allowlist,
                    batcher=batcher,
                    analysis_state=analysis_state,
                )
            else:
                await _emit_partial(websocket, session, result)
    except STTUnavailable as exc:
        logger.warning("stt_unavailable", reason=exc.reason, mode=exc.degraded_mode)
        await session.set_mode(LiveSessionManager.MODE_RECORD_ONLY)
        await _send_error_frame(websocket, session, exc.reason)
        recovery = asyncio.create_task(
            _stt_recovery_task(
                websocket,
                session,
                stt,
                codec=codec,
                sample_rate=sample_rate,
                stt_state=stt_state,
            )
        )
        stt_state["recovery_task"] = recovery
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("stt_loop_failed", error=f"{type(exc).__name__}: {exc}")
        await session.set_mode(LiveSessionManager.MODE_RECORD_ONLY)
        await _send_error_frame(
            websocket, session, "Transcription temporarily unavailable."
        )


async def _send_error_frame(
    websocket: WebSocket, session: LiveSessionManager, message: str
) -> None:
    """Best-effort ERR-07 delivery; swallows failures (Redis may be down)."""
    try:
        seq = await session.next_seq()
        err = ErrorFrame(
            seq=seq,
            code="ERR-07",
            message=message,
            recoverable=True,
        )
        payload = await session.emit(err)
        await websocket.send_json(payload)
    except Exception:  # noqa: BLE001
        pass


async def _send_recovery_frame(
    websocket: WebSocket,
    session: LiveSessionManager,
    dependency: str,
    message: str,
) -> None:
    """Best-effort recovery notification; swallows failures."""
    try:
        seq = await session.next_seq()
        frame = RecoveryFrame(
            seq=seq,
            dependency=dependency,
            message=message,
        )
        payload = await session.emit(frame)
        await websocket.send_json(payload)
    except Exception:  # noqa: BLE001
        pass


async def _stt_recovery_task(
    websocket: WebSocket,
    session: LiveSessionManager,
    stt: STTAdapter,
    *,
    codec: str,
    sample_rate: int,
    stt_state: dict[str, Any],
) -> None:
    """Periodically probe STT until the breaker closes (F-06 §18.2).

    After ``reset_timeout_seconds`` (60 s by default), the breaker moves to
    HALF_OPEN and allows a trial call. If the probe succeeds, the breaker
    closes, mode returns to NORMAL, a recovery frame is sent, and a new
    STT loop is spawned with a fresh audio queue.
    """
    registry: BreakerRegistry | None = getattr(websocket.app.state, "breakers", None)
    breaker = registry.get("stt") if registry else None
    poll_s = float(breaker.config.reset_timeout_seconds if breaker else 60)

    try:
        while True:
            await asyncio.sleep(poll_s)

            if breaker:
                try:
                    breaker.before_call()
                except CircuitBreakerOpen:
                    continue

            async def _probe_audio() -> AsyncIterator[bytes]:
                yield b"\x00" * 320
                return

            try:
                async for _ in stt.stream(
                    _probe_audio(), sample_rate=sample_rate, codec=codec
                ):
                    break
            except STTUnavailable:
                logger.info("stt_recovery_probe_failed")
                continue
            except Exception:  # noqa: BLE001
                logger.info("stt_recovery_probe_error")
                continue

            await session.set_mode(LiveSessionManager.MODE_NORMAL)
            await _send_recovery_frame(
                websocket,
                session,
                "stt",
                "Live transcription resumed.",
            )
            logger.info("stt_recovered")

            audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
            task = asyncio.create_task(
                _stt_loop(
                    websocket,
                    session,
                    stt,
                    audio_q,
                    codec=codec,
                    sample_rate=sample_rate,
                    stt_state=stt_state,
                )
            )
            stt_state["audio_q"] = audio_q
            stt_state["stt_task"] = task
            task.add_done_callback(lambda _: stt_state.update(audio_q=None))
            return
    except asyncio.CancelledError:
        pass


async def _emit_partial(
    websocket: WebSocket, session: LiveSessionManager, result: STTResult
) -> None:
    """AC-1: partials within 2 s, no LLM/redaction pass."""
    try:
        seq = await session.next_seq()
        frame = TranscriptPartial(seq=seq, text=result.text, speaker=0)
        payload = await session.emit(frame)
        await websocket.send_json(payload)
    except WebSocketDisconnect:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("emit_partial_failed")


async def _emit_final(
    websocket: WebSocket,
    session: LiveSessionManager,
    result: STTResult,
    *,
    recording_id: str = "",
    allowlist: list[str] | None = None,
    batcher: SegmentBatcher | None = None,
    analysis_state: dict[str, Any] | None = None,
) -> None:
    """AC-4: persisted redacted, displayed unredacted.

    Two frames from one STT result: the redacted one goes to Redis (the
    replay buffer, the analysis loop, anything that stores or reasons about
    the text), and the unredacted one goes to the client who is hearing the
    words live and does not benefit from seeing ``<PHONE_NUMBER>`` on screen.

    G-01: emits EVT-103 with entity types (never text or values).
    G-02: feeds finalized segments to the batcher for analysis.
    """
    try:
        seq = await session.next_seq()
    except Exception:  # noqa: BLE001
        logger.warning("emit_final_seq_failed")
        return

    try:
        redaction = redact_text(result.text, allowlist=allowlist)
    except Exception:  # noqa: BLE001
        logger.warning("redact_text_failed", text_len=len(result.text))
        redaction = RedactionResult(text=result.text, applied=False)

    buffered = TranscriptFinal(
        seq=seq,
        text=redaction.text,
        speaker=0,
        t_start=result.t_start,
        t_end=result.t_end,
        redaction_applied=redaction.applied,
    )
    try:
        await session.emit(buffered)
    except Exception:  # noqa: BLE001
        logger.warning("emit_final_buffer_failed", seq=seq)

    displayed = TranscriptFinal(
        seq=seq,
        text=result.text,
        speaker=0,
        t_start=result.t_start,
        t_end=result.t_end,
        redaction_applied=False,
    )
    try:
        await websocket.send_json(displayed.model_dump(mode="json"))
    except WebSocketDisconnect:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("emit_final_send_failed", seq=seq)

    await _emit_evt103(
        websocket,
        session,
        recording_id=recording_id,
        seq=seq,
        redaction_applied=redaction.applied,
        entity_types=redaction.entity_types,
    )

    if batcher is not None:
        segment = {
            "text": redaction.text,
            "speaker": 0,
            "t_start": result.t_start,
            "t_end": result.t_end,
        }
        batch = batcher.add(segment)
        if batch is not None:
            _spawn_analysis(websocket, session, batch, analysis_state)


async def _emit_evt103(
    websocket: WebSocket,
    session: LiveSessionManager,
    *,
    recording_id: str,
    seq: int,
    redaction_applied: bool,
    entity_types: list[str],
) -> None:
    """EVT-103: segment finalised — entity types only, never text or values."""
    events = getattr(websocket.app.state, "events", None)
    if events is None:
        return
    try:
        await events.emit(
            EventType.TRANSCRIPT_SEGMENT_FINALIZED,
            tenant_id=session.tenant_id,
            correlation_id=session.session_id,
            session_id=session.session_id,
            payload={
                "recording_id": recording_id,
                "seq": seq,
                "redaction_applied": redaction_applied,
                "entity_types": entity_types,
            },
            outcome="SUCCESS",
        )
    except Exception:  # noqa: BLE001
        logger.warning("evt103_emission_failed", seq=seq)


def _spawn_analysis(
    websocket: WebSocket,
    session: LiveSessionManager,
    batch: SegmentBatch,
    analysis_state: dict[str, Any] | None,
) -> None:
    """Fire-and-forget analysis task for a batch (G-02 AC-2).

    Runs in a separate asyncio task so the STT pipeline is never blocked.
    Only one analysis runs at a time — a new batch cancels any in-flight
    task so orphaned tasks cannot accumulate.
    """
    if analysis_state is None:
        return
    prev = analysis_state.get("task")
    if prev is not None and not prev.done():
        prev.cancel()
    task = asyncio.create_task(_run_analysis(websocket, session, batch, analysis_state))
    analysis_state["task"] = task


async def _run_analysis(
    websocket: WebSocket,
    session: LiveSessionManager,
    batch: SegmentBatch,
    analysis_state: dict[str, Any],
) -> None:
    """Map a transcript batch onto prepared questions and score sufficiency.

    G-02: SKL-OIA-04 maps batch → question attachments.
    G-03: SKL-OIA-05 scores sufficiency for each question that received new
    evidence; emits GreenSignal frames when the threshold is met.

    AC-3 (timeout): late results are discarded, not delayed.
    AC-4 (breaker): when the LLM breaker is open, analysis is skipped entirely.
    """
    registry: SkillRegistry | None = analysis_state.get("skill_registry")
    events = analysis_state.get("events")
    breaker_registry: BreakerRegistry | None = analysis_state.get("breakers")

    if registry is None:
        return

    llm_breaker = breaker_registry.get("llm") if breaker_registry else None
    if llm_breaker and llm_breaker.state is State.OPEN:
        if not analysis_state.get("degraded_sent"):
            msg = llm_breaker.config.user_message or (
                "Suggestions paused. Check questions off manually."
            )
            await _send_degraded_frame(websocket, session, msg)
            analysis_state["degraded_sent"] = True
        return

    if analysis_state.get("degraded_sent"):
        analysis_state["degraded_sent"] = False

    context = SkillContext(
        input_prompt="Map transcript to questions",
        input_context={
            "segments": batch.segments,
            "question_states": await session.get_questions(),
            "recording_id": batch.recording_id,
        },
        tenant_context=TenantContext(tenant_id=session.tenant_id, role="ADMIN"),
        origin=Origin.INTERNAL,
    )

    try:
        chunks = await asyncio.wait_for(
            _collect_skill_stream(registry, context),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "analysis_timeout",
            session=session.session_id,
            batch_first_t=batch.first_t,
        )
        if events:
            try:
                await events.emit(
                    EventType.AGENT_FAILED,
                    tenant_id=session.tenant_id,
                    correlation_id=session.session_id,
                    session_id=session.session_id,
                    payload={
                        "skill": "SKL-OIA-04",
                        "reason": "timeout",
                        "batch_first_t": batch.first_t,
                        "batch_last_t": batch.last_t,
                    },
                    outcome="TIMEOUT",
                )
            except Exception:  # noqa: BLE001
                pass
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning("analysis_failed", error=f"{type(exc).__name__}: {exc}")
        return

    has_attachment = False
    updated_questions: list[str] = []
    for chunk in chunks:
        chunk_type = chunk.get("type", "")
        if chunk_type == "attachment":
            has_attachment = True
            qid = chunk.get("question_id", "")
            evidence = chunk.get("evidence", [])
            relevance = chunk.get("relevance", 0.0)
            if qid and evidence:
                await session.store_analysis_result(qid, evidence, relevance)
                updated_questions.append(qid)
        elif chunk_type == "notable_fact":
            pass

    if not has_attachment:
        await session.store_unmapped_batch(batch.segments)

    # G-03: score sufficiency for each question that received new evidence.
    if updated_questions:
        await _evaluate_sufficiency(
            websocket,
            session,
            registry,
            events,
            updated_questions,
            context.tenant_context,
        )


async def _collect_skill_stream(
    registry: SkillRegistry, context: SkillContext
) -> list[dict[str, Any]]:
    """Collect the skill stream into a list so wait_for can timeout it."""
    chunks: list[dict[str, Any]] = []
    async for chunk in registry.execute_stream("SKL-OIA-04", context):
        chunks.append(chunk)
    return chunks


async def _evaluate_sufficiency(
    websocket: WebSocket,
    session: LiveSessionManager,
    registry: SkillRegistry,
    events: Any,
    question_ids: list[str],
    tenant_context: TenantContext,
) -> None:
    """Score sufficiency for each question that received new evidence (G-03).

    Skips questions that are already GREEN (sticky) or manually overridden.
    Captures the question version before scoring; applies the green signal
    only if the version hasn't changed (AC-3 ordering hazard).
    """
    from app.core.config import get_settings

    cfg = get_settings()
    threshold = cfg.SUFFICIENCY_GREEN_THRESHOLD

    for qid in question_ids:
        entry = await session.get_question_entry(qid)
        if entry is None:
            continue

        if entry.get("status") == "GREEN":
            continue
        if entry.get("source") == "manual":
            continue

        expected_version = entry.get("version", 0)
        evidence_spans = entry.get("evidence", [])

        if not evidence_spans:
            continue

        suf_context = SkillContext(
            input_prompt="Score answer sufficiency",
            input_context={
                "question": entry.get("text", ""),
                "attached_spans": evidence_spans,
                "target_field": entry.get("target_field", ""),
            },
            tenant_context=tenant_context,
            origin=Origin.INTERNAL,
            config={"sufficiency_green_threshold": threshold},
        )

        try:
            chunks: list[dict[str, Any]] = []
            async for chunk in asyncio.wait_for(
                _collect_sufficiency_stream(registry, suf_context),
                timeout=5.0,
            ):
                chunks.append(chunk)
        except asyncio.TimeoutError:
            logger.warning(
                "sufficiency_timeout",
                session=session.session_id,
                question_id=qid,
            )
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "sufficiency_failed",
                question_id=qid,
                error=f"{type(exc).__name__}: {exc}",
            )
            continue

        for chunk in chunks:
            if chunk.get("type") != "sufficiency_result":
                continue

            score = chunk.get("sufficiency_score", 0.0)
            is_green = chunk.get("green", False)
            missing = chunk.get("missing_aspects", [])
            ev_spans = chunk.get("evidence", [])

            if is_green and ev_spans:
                applied = await session.apply_green_signal(
                    qid,
                    score,
                    ev_spans,
                    expected_version,
                )
                if applied:
                    await _send_green_signal(
                        websocket,
                        session,
                        events,
                        qid,
                        score,
                        ev_spans,
                    )
            else:
                await session.update_sufficiency(qid, score, missing)


async def _collect_sufficiency_stream(
    registry: SkillRegistry, context: SkillContext
) -> AsyncIterator[dict[str, Any]]:
    """Yield SKL-OIA-05 chunks for async iteration inside wait_for."""
    async for chunk in registry.execute_stream("SKL-OIA-05", context):
        yield chunk


async def _send_green_signal(
    websocket: WebSocket,
    session: LiveSessionManager,
    events: Any,
    question_id: str,
    score: float,
    evidence_spans: list[dict[str, Any]],
) -> None:
    """Emit a GreenSignal frame and EVT-104."""
    try:
        seq = await session.next_seq()
        frame = GreenSignal(
            seq=seq,
            question_id=question_id,
            score=score,
            evidence=[
                EvidenceSpan(
                    recording_id=s.get("recording_id", ""),
                    t_start=s.get("t_start", 0.0),
                    t_end=s.get("t_end", 0.0),
                )
                for s in evidence_spans
                if s.get("recording_id")
            ],
        )
        payload = await session.emit(frame)
        await websocket.send_json(payload)
    except Exception:  # noqa: BLE001
        logger.warning("green_signal_send_failed", question_id=question_id)
        return

    if events:
        try:
            await events.emit(
                EventType.SUFFICIENCY_SIGNAL,
                tenant_id=session.tenant_id,
                correlation_id=session.session_id,
                session_id=session.session_id,
                payload={
                    "question_id": question_id,
                    "score": score,
                    "green": True,
                    "evidence_span_count": len(evidence_spans),
                },
                outcome="SUCCESS",
            )
        except Exception:  # noqa: BLE001
            logger.warning("evt104_emission_failed", question_id=question_id)


async def _send_degraded_frame(
    websocket: WebSocket, session: LiveSessionManager, message: str
) -> None:
    """Send the LLM degraded-mode message once (AC-4)."""
    try:
        seq = await session.next_seq()
        err = ErrorFrame(
            seq=seq,
            code="ERR-08",
            message=message,
            recoverable=True,
        )
        payload = await session.emit(err)
        await websocket.send_json(payload)
    except Exception:  # noqa: BLE001
        pass


async def _cancel_recovery(stt_state: dict[str, Any]) -> None:
    """Cancel a pending recovery task and clear its slot."""
    recovery = stt_state.get("recovery_task")
    if recovery is not None and not recovery.done():
        recovery.cancel()
        try:
            await recovery
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
    stt_state["recovery_task"] = None


async def _handle_control(
    websocket: WebSocket,
    session: Any,
    message: Any,
    *,
    stt_state: dict[str, Any],
) -> None:
    """Act on one client control frame (§10.2.3).

    ``start`` creates the audio queue and spawns the STT loop.
    ``stop`` sends the sentinel that drains and closes the STT stream.
    ``resume`` replays buffered frames.
    ``mark_question`` is parsed and acknowledged by silence — G-03 gives it
    behaviour.

    Malformed input is ignored, never fatal. A client bug must not end a
    meeting that is otherwise recording fine.
    """
    if session is None:
        return
    raw = message.get("text")
    if not raw:
        return

    try:
        frame = json.loads(raw)
    except (TypeError, ValueError):
        logger.info("live_control_unparseable")
        return

    if not isinstance(frame, dict):
        return

    frame_type = frame.get("type")

    if frame_type == ClientFrameType.START.value:
        try:
            start = StartFrame(**frame)
        except ValidationError:
            logger.info("live_start_malformed")
            return

        if stt_state.get("audio_q") is not None:
            return

        await _cancel_recovery(stt_state)

        stt: STTAdapter | None = getattr(websocket.app.state, "stt", None)
        if stt is None:
            logger.warning("stt_not_configured")
            return

        stt_state["recording_id"] = start.recording_id

        batcher_obj = stt_state.get("batcher")
        if batcher_obj is not None:
            batcher_obj.recording_id = start.recording_id

        audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        task = asyncio.create_task(
            _stt_loop(
                websocket,
                session,
                stt,
                audio_q,
                codec=start.codec,
                sample_rate=start.sample_rate,
                stt_state=stt_state,
            )
        )
        stt_state["audio_q"] = audio_q
        stt_state["stt_task"] = task
        task.add_done_callback(lambda _: stt_state.update(audio_q=None))
        logger.info(
            "stt_started",
            codec=start.codec,
            sample_rate=start.sample_rate,
            recording_id=start.recording_id,
        )
        return

    if frame_type == ClientFrameType.STOP.value:
        await _cancel_recovery(stt_state)
        pending_q = stt_state.get("audio_q")
        if pending_q is not None:
            pending_q.put_nowait(None)
            stt_state["audio_q"] = None
            pending_task = stt_state.get("stt_task")
            if pending_task is not None and not pending_task.done():
                try:
                    await asyncio.wait_for(pending_task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pending_task.cancel()
                    try:
                        await pending_task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
            stt_state["stt_task"] = None
        logger.info("stt_stopped")
        return

    if frame_type == ClientFrameType.MARK_QUESTION.value:
        try:
            mark = MarkQuestionFrame(**frame)
        except ValidationError:
            logger.info("live_mark_question_malformed")
            return
        await session.mark_question(mark.question_id, mark.action)
        logger.info(
            "mark_question_stored",
            question_id=mark.question_id,
            action=mark.action,
        )
        return

    if frame_type == ClientFrameType.RESUME.value:
        try:
            resume = ResumeFrame(**frame)
        except ValidationError:
            logger.info("live_resume_malformed")
            return

        frames, resync = await session.replay_after(resume.last_seq)
        if resync is not None:
            await websocket.send_json(resync.model_dump(mode="json"))
            return

        for replayed in frames:
            await websocket.send_json(replayed)
        return


async def _hold(
    websocket: WebSocket,
    verdict: Handshake,
    lock: LiveLock | None,
    backend: Any,
    session_id: str,
    ticket: str,
    precheck_data: dict[str, Any] | None = None,
) -> None:
    """Keep the socket open while it remains authorised.

    Two things can end a live meeting from the server side, and NFR-SEC-02
    insists neither waits for traffic: the authorisation expiring, and consent
    being revoked. "A token that expires mid-session closes the socket with
    4401, **not at the next message boundary**" — an idle socket is exactly
    the case that matters, because a meeting where nobody is speaking still
    holds a connection.

    One poll covers both, and refreshes the lock on the same tick. Three
    timers would be three things to get wrong.
    """
    # Injected through app.state, like `backend` and `redis`. A test that had
    # to wait a real thirty seconds per iteration is a test nobody runs, and
    # patching the module constant would leave the production path untested.
    poll_s = float(getattr(websocket.app.state, "live_poll_s", REFRESH_S))

    redis_manager = getattr(websocket.app.state, "redis", None)
    session = (
        LiveSessionManager(
            redis=redis_manager,
            tenant_id=verdict.tenant_id,
            session_id=session_id,
        )
        if redis_manager is not None
        else None
    )

    allowlist = [t for t in [verdict.company_name] if t]
    if session is not None and allowlist:
        try:
            await session.set_allowlist(allowlist)
        except Exception:  # noqa: BLE001
            logger.warning("set_allowlist_failed")

    # G-02: store approved questions from precheck for analysis mapping
    questions = []
    if precheck_data and precheck_data.get("questions"):
        questions = precheck_data["questions"]
    if session is not None and questions:
        try:
            await session.set_questions(questions)
        except Exception:  # noqa: BLE001
            logger.warning("set_questions_failed")

    # G-02: batcher and analysis state
    from app.core.config import get_settings

    cfg = get_settings()
    batcher = SegmentBatcher(
        window_s=cfg.BATCH_WINDOW_S,
        min_duration_s=cfg.BATCH_MIN_DURATION_S,
    )

    skill_registry: SkillRegistry | None = getattr(
        websocket.app.state, "skill_registry", None
    )
    events = getattr(websocket.app.state, "events", None)
    breaker_registry: BreakerRegistry | None = getattr(
        websocket.app.state, "breakers", None
    )

    analysis_state: dict[str, Any] = {
        "skill_registry": skill_registry,
        "events": events,
        "breakers": breaker_registry,
        "task": None,
        "degraded_sent": False,
    }

    stt_state: dict[str, Any] = {
        "audio_q": None,
        "stt_task": None,
        "recovery_task": None,
        "allowlist": allowlist,
        "batcher": batcher,
        "analysis_state": analysis_state,
    }
    _breaker_cb = None
    _breaker_ref = None
    if breaker_registry and events:
        _breaker_ref = breaker_registry.get("stt")

        def _on_breaker_change(dep: str, old: State, new: State) -> None:
            if new is State.OPEN:
                event_type = EventType.AGENT_CIRCUIT_OPENED
            elif new is State.CLOSED:
                event_type = EventType.AGENT_CIRCUIT_CLOSED
            else:
                return
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    events.emit(
                        event_type,
                        tenant_id=verdict.tenant_id,
                        correlation_id=session_id,
                        session_id=session_id,
                        payload={
                            "dependency": dep,
                            "from_state": old.value,
                            "to_state": new.value,
                        },
                        outcome="DEGRADED" if new is State.OPEN else "SUCCESS",
                    )
                )
            except Exception:  # noqa: BLE001
                pass

        _breaker_cb = _on_breaker_change
        _breaker_ref.add_on_state_change(_breaker_cb)

    try:
        while True:
            if expired(verdict.valid_until):
                await websocket.close(
                    code=CLOSE_UNAUTHORIZED,
                    reason="Session authorisation expired.",
                )
                return

            if lock is not None and not await lock.refresh():
                await websocket.close(
                    code=CLOSE_CONFLICT,
                    reason="Another socket took over this session.",
                )
                return

            state = await fetch_consent_state(
                backend,
                tenant_id=verdict.tenant_id,
                session_id=session_id,
            )
            refusal = consent_verdict(state)
            if refusal.blocked:
                await websocket.close(code=CLOSE_FORBIDDEN, reason=refusal.detail[:120])
                return

            # G-02: check batcher timer on each poll cycle
            timer_batch = batcher.check_timer()
            if timer_batch is not None and session is not None:
                _spawn_analysis(websocket, session, timer_batch, analysis_state)

            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=poll_s)
            except asyncio.TimeoutError:
                continue
            except (WebSocketDisconnect, RuntimeError):
                return

            if message.get("type") == "websocket.disconnect":
                return

            # Binary audio → STT queue (F-05)
            if message.get("bytes") and stt_state.get("audio_q") is not None:
                stt_state["audio_q"].put_nowait(message["bytes"])
                continue

            await _handle_control(websocket, session, message, stt_state=stt_state)
    finally:
        if _breaker_ref is not None and _breaker_cb is not None:
            _breaker_ref.remove_on_state_change(_breaker_cb)

        # G-02: flush remaining segments; let the final analysis finish
        final_batch = batcher.flush()
        if final_batch is not None and session is not None:
            _spawn_analysis(websocket, session, final_batch, analysis_state)

        analysis_task = analysis_state.get("task")
        if analysis_task is not None and not analysis_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(analysis_task), timeout=5.0)
            except (
                asyncio.TimeoutError,
                asyncio.CancelledError,
                Exception,
            ):  # noqa: BLE001
                analysis_task.cancel()
                try:
                    await analysis_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass

        audio_q = stt_state.get("audio_q")
        if audio_q is not None:
            audio_q.put_nowait(None)
        for key in ("stt_task", "recovery_task"):
            task = stt_state.get(key)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
