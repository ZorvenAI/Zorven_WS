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
    ResumeFrame,
    StartFrame,
    TranscriptFinal,
    TranscriptPartial,
)
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
from app.logic.live_session import LiveSessionManager
from app.providers.stt import STTAdapter, STTResult, STTUnavailable
from app.skills.redact_pii import redact_text

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
        await _hold(websocket, verdict, lock, backend, session_id, ticket)
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
) -> None:
    """Background task: feed audio to STT, emit frames.

    Partials go to the client as-is — no LLM, no redaction (§4.3).
    Finals are redacted before buffering (IG-04/SKL-OIA-16) but sent
    unredacted to the client who is hearing the conversation live.
    """
    try:
        async for result in stt.stream(
            _audio_from_queue(audio_q),
            sample_rate=sample_rate,
            codec=codec,
        ):
            if result.is_final:
                await _emit_final(websocket, session, result)
            else:
                await _emit_partial(websocket, session, result)
    except STTUnavailable as exc:
        logger.warning("stt_unavailable", reason=exc.reason, mode=exc.degraded_mode)
        await _send_error_frame(websocket, session, exc.reason)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("stt_loop_failed", error=f"{type(exc).__name__}: {exc}")
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
    websocket: WebSocket, session: LiveSessionManager, result: STTResult
) -> None:
    """AC-4: persisted redacted, displayed unredacted.

    Two frames from one STT result: the redacted one goes to Redis (the
    replay buffer, the analysis loop, anything that stores or reasons about
    the text), and the unredacted one goes to the client who is hearing the
    words live and does not benefit from seeing ``<PHONE_NUMBER>`` on screen.
    """
    try:
        seq = await session.next_seq()
    except Exception:  # noqa: BLE001
        logger.warning("emit_final_seq_failed")
        return

    try:
        redacted = redact_text(result.text)
    except Exception:  # noqa: BLE001
        logger.warning("redact_text_failed", text_len=len(result.text))
        redacted = result.text

    buffered = TranscriptFinal(
        seq=seq,
        text=redacted,
        speaker=0,
        t_start=result.t_start,
        t_end=result.t_end,
        redaction_applied=redacted != result.text,
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
    await websocket.send_json(displayed.model_dump(mode="json"))


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

        stt: STTAdapter | None = getattr(websocket.app.state, "stt", None)
        if stt is None:
            logger.warning("stt_not_configured")
            return

        audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
        task = asyncio.create_task(
            _stt_loop(
                websocket,
                session,
                stt,
                audio_q,
                codec=start.codec,
                sample_rate=start.sample_rate,
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
        audio_q = stt_state.get("audio_q")
        if audio_q is not None:
            audio_q.put_nowait(None)
            stt_state["audio_q"] = None
            task = stt_state.get("stt_task")
            if task is not None and not task.done():
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass
            stt_state["stt_task"] = None
        logger.info("stt_stopped")
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

    stt_state: dict[str, Any] = {"audio_q": None, "stt_task": None}

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
        audio_q = stt_state.get("audio_q")
        if audio_q is not None:
            audio_q.put_nowait(None)
        task = stt_state.get("stt_task")
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
