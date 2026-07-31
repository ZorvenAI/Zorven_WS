"""Throwaway echo service for spike A-02.

Stands in for the future ``WS /v1/live/{session_id}`` endpoint so the gateway
behaviour can be measured without STT, Redis, Gemini or any other dependency.
It implements exactly the parts of Design §10.2.3 that the gateway can affect:
the handshake, the close codes, the monotonic seq series and reconnect replay.

This service is deliberately **not** wired into docker-compose, CI or the
Cloud Run deploy matrix. It is deleted when the spike closes.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .auth import AuthError, TenantClaims, authenticate
from .frames import CloseCode, EchoAck, Resync, SeqAllocator, TranscriptPartial
from .replay import ReplayBuffer

JWT_SECRET = os.environ.get(
    "OIA_SPIKE_JWT_SECRET", "dev-secret-key-change-in-production"
)
JWT_ISSUER = os.environ.get("OIA_SPIKE_JWT_ISSUER", "ai-brand-automator")
REPLAY_CAPACITY = int(os.environ.get("OIA_SPIKE_REPLAY_CAPACITY", "512"))

# Identifies this process. Cloud Run may answer two connections from two
# different instances, and in-process session state does not survive that —
# which is precisely why F-04 keeps the replay buffer in Redis.
INSTANCE_ID = f"{os.environ.get('K_REVISION', 'local')}-{uuid.uuid4().hex[:8]}"

# A session id with this prefix is treated as unknown, so the 4404 path can be
# exercised without a database.
UNKNOWN_SESSION_PREFIX = "missing-"


@dataclass
class SessionState:
    """Per-session state that survives reconnects within the process life.

    The seq series continues across a reconnect rather than restarting — that
    is what makes replay meaningful (Design §9.2).
    """

    seq: SeqAllocator = field(default_factory=SeqAllocator)
    buffer: ReplayBuffer = field(default_factory=lambda: ReplayBuffer(REPLAY_CAPACITY))
    socket_open: bool = False


@dataclass
class Stats:
    """Counters the harness reads to prove where a rejection happened.

    ``handshakes_seen`` increments the moment a request reaches this service,
    before any authentication. If Kong rejects a bad token at the gateway,
    this counter must not move — that is the difference between "the gateway
    rejected it" and "the service rejected it", and asserting on the close
    code alone cannot tell them apart.
    """

    handshakes_seen: int = 0
    handshakes_accepted: int = 0
    rejected_4401: int = 0
    rejected_4404: int = 0
    rejected_4409: int = 0
    binary_frames: int = 0
    bytes_received: int = 0


app = FastAPI(title="A-02 gateway WebSocket spike — echo service")
sessions: dict[str, SessionState] = {}
stats = Stats()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "spike-ws-gateway-echo", "instance": INSTANCE_ID}


@app.get("/health/stats")
async def health_stats() -> dict:
    return {
        "handshakes_seen": stats.handshakes_seen,
        "handshakes_accepted": stats.handshakes_accepted,
        "rejected_4401": stats.rejected_4401,
        "rejected_4404": stats.rejected_4404,
        "rejected_4409": stats.rejected_4409,
        "binary_frames": stats.binary_frames,
        "bytes_received": stats.bytes_received,
        "live_sessions": sum(1 for s in sessions.values() if s.socket_open),
        "instance": INSTANCE_ID,
    }


@app.post("/health/reset")
async def health_reset() -> dict:
    """Clear counters and session state between measurement runs."""
    global stats
    stats = Stats()
    sessions.clear()
    return {"status": "reset"}


async def _reject(ws: WebSocket, code: CloseCode) -> None:
    """Refuse a socket while still delivering the §10.2.3 close code.

    A spike finding that F-04 inherits: closing *before* ``accept()`` makes
    Starlette answer the handshake with plain HTTP 403, and the client never
    sees the code — the WebSocket protocol has nowhere to put a close code
    until the upgrade has completed. Delivering 4401/4403/4404/4409/4429 at
    all therefore requires accepting first and closing immediately after.

    The authorisation decision is still made before ``accept()``; only the
    delivery of the verdict happens after it. No frame is ever read from, or
    sent to, a socket rejected here.
    """
    await ws.accept()
    await ws.close(code=code)


async def _send(ws: WebSocket, state: SessionState, frame) -> dict:
    """Emit one server → client frame, allocating its seq and buffering it."""
    payload = frame.model_dump() if hasattr(frame, "model_dump") else dict(frame)
    payload["seq"] = state.seq.next()
    state.buffer.append(payload)
    await ws.send_json(payload)
    return payload


@app.websocket("/v1/live/{session_id}")
async def live(ws: WebSocket, session_id: str) -> None:
    # Counted before authentication: see Stats.handshakes_seen.
    stats.handshakes_seen += 1

    try:
        claims: TenantClaims = authenticate(
            dict(ws.query_params),
            list(ws.scope.get("subprotocols") or []),
            JWT_SECRET,
            expected_issuer=JWT_ISSUER,
        )
    except AuthError:
        stats.rejected_4401 += 1
        await _reject(ws, CloseCode.INVALID_JWT)
        return

    if session_id.startswith(UNKNOWN_SESSION_PREFIX):
        stats.rejected_4404 += 1
        await _reject(ws, CloseCode.SESSION_NOT_FOUND)
        return

    state = sessions.setdefault(session_id, SessionState())

    # One live socket per session, decisively: the newcomer is closed and the
    # incumbent is left untouched (F-04 AC-2).
    if state.socket_open:
        stats.rejected_4409 += 1
        await _reject(ws, CloseCode.ALREADY_LIVE)
        return

    await ws.accept()
    state.socket_open = True
    stats.handshakes_accepted += 1

    try:
        await _run_session(ws, state, claims)
    except WebSocketDisconnect:
        pass
    finally:
        state.socket_open = False
        if ws.client_state is WebSocketState.CONNECTED:
            await ws.close()


async def _run_session(
    ws: WebSocket, state: SessionState, claims: TenantClaims
) -> None:
    while True:
        message = await ws.receive()

        if message["type"] == "websocket.disconnect":
            return

        if (data := message.get("bytes")) is not None:
            stats.binary_frames += 1
            stats.bytes_received += len(data)
            # The harness prefixes each audio-sized frame with an 8-byte
            # big-endian id so round-trip time can be paired exactly rather
            # than inferred from ordering.
            echo_id = int.from_bytes(data[:8], "big") if len(data) >= 8 else -1
            await _send(
                ws,
                state,
                EchoAck(
                    seq=0,
                    echo_id=echo_id,
                    bytes_received=len(data),
                    instance=INSTANCE_ID,
                ),
            )
            continue

        text = message.get("text")
        if text is None:
            continue

        await _handle_control(ws, state, claims, text)


async def _handle_control(
    ws: WebSocket, state: SessionState, claims: TenantClaims, text: str
) -> None:
    import json

    try:
        control = json.loads(text)
    except json.JSONDecodeError:
        return

    kind = control.get("type")

    if kind == "resume":
        last_seq = int(control.get("last_seq", -1))
        result = state.buffer.resume(last_seq)
        if result.resync_required:
            await _send(
                ws,
                state,
                Resync(
                    seq=0,
                    reason="last_seq predates the retained replay window",
                    oldest_available_seq=result.oldest_available_seq,
                ),
            )
            return
        # Replayed frames keep their original seq — the series does not
        # restart and no seq is minted twice.
        for frame in result.frames:
            await ws.send_json(frame)
        return

    if kind == "start":
        await _send(
            ws,
            state,
            TranscriptPartial(
                seq=0,
                text=f"session started for tenant {claims.tenant_id}",
                speaker=0,
            ),
        )
        return

    if kind == "heartbeat":
        # Spike-only: lets the harness prove an application-level 20s
        # heartbeat keeps the socket alive through the gateway.
        await _send(
            ws,
            state,
            EchoAck(seq=0, echo_id=-1, bytes_received=0, instance=INSTANCE_ID),
        )
        return

    if kind == "stop":
        await ws.close()
        return
