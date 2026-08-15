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
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.api.schemas import ClientFrameType, ResumeFrame
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


async def _handle_control(websocket: WebSocket, session: Any, message: Any) -> None:
    """Act on one client control frame (§10.2.3).

    Only `resume` does anything in PR 2. `start`, `mark_question` and `stop`
    are parsed and acknowledged by silence rather than rejected — F-05 and
    G-03 give them behaviour, and refusing a frame the protocol defines would
    make this socket wrong for the client rather than merely incomplete.

    Malformed input is ignored, never fatal. A client bug must not end a
    meeting that is otherwise recording fine.
    """
    if session is None:
        return
    raw = message.get("text")
    if not raw:
        # Binary audio carries no envelope (§10.2.3). F-05 consumes it.
        return

    try:
        frame = json.loads(raw)
    except (TypeError, ValueError):
        logger.info("live_control_unparseable")
        return

    if not isinstance(frame, dict) or frame.get("type") != ClientFrameType.RESUME.value:
        return

    try:
        resume = ResumeFrame(**frame)
    except ValidationError:
        logger.info("live_resume_malformed")
        return

    frames, resync = await session.replay_after(resume.last_seq)
    if resync is not None:
        # AC-3: an explicit frame, never a silent gap. The client is told
        # where the record now starts rather than left to infer it.
        await websocket.send_json(resync.model_dump(mode="json"))
        return

    for replayed in frames:
        await websocket.send_json(replayed)


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

    while True:
        if expired(verdict.valid_until):
            await websocket.close(
                code=CLOSE_UNAUTHORIZED, reason="Session authorisation expired."
            )
            return

        if lock is not None and not await lock.refresh():
            # The claim lapsed and somebody else has it. Ours is the socket
            # that must go: two writers on one meeting is the state AC-2
            # exists to prevent.
            await websocket.close(
                code=CLOSE_CONFLICT, reason="Another socket took over this session."
            )
            return

        state = await fetch_consent_state(
            backend, tenant_id=verdict.tenant_id, session_id=session_id
        )
        refusal = consent_verdict(state)
        if refusal.blocked:
            # F-01 AC-4, finally reachable end to end: a revocation closes an
            # open socket rather than being noticed at the next message.
            await websocket.close(code=CLOSE_FORBIDDEN, reason=refusal.detail[:120])
            return

        try:
            message = await asyncio.wait_for(websocket.receive(), timeout=poll_s)
        except asyncio.TimeoutError:
            # Idle. Looping is the point — the checks above are what an idle
            # socket exists to keep running.
            continue
        except (WebSocketDisconnect, RuntimeError):
            return

        # `receive()` *returns* the disconnect rather than raising it, which is
        # easy to miss and expensive to get wrong: without this the loop spins
        # for the life of the process after the client has gone, holding the
        # company's live lock and polling Django every few seconds. It showed
        # up as a test suite that hung rather than failed.
        if message.get("type") == "websocket.disconnect":
            return

        await _handle_control(websocket, session, message)
