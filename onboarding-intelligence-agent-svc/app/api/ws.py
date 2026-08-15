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

from fastapi import APIRouter, WebSocket

from app.core.logging import get_logger
from app.logic.consent_gate import (
    CLOSE_FORBIDDEN,
    consent_verdict,
    emit_refusal,
    fetch_consent_state,
)
from app.logic.live_gate import evaluate

logger = get_logger(__name__)

router = APIRouter()

#: §10.2.3. Sent when the socket is refused for want of a tenant to check.
CLOSE_UNAUTHORIZED = 4401


def _tenant_of(websocket: WebSocket) -> str:
    """The tenant this socket claims.

    Read from the query string, and that is a deliberate limitation of a
    gate-only endpoint rather than a decision about authentication. §15 is
    clear that a role and a tenant come from a verified claim; F-04 must
    resolve this from the ``?jwt=`` token before any data flows.

    It is safe *here* because the only thing this endpoint does with it is
    decide whether to refuse. A caller who names another tenant's session gets
    the same refusal as one who names nothing — the precheck is tenant-scoped
    in Django and answers 404 for a session outside it, which this turns into
    a refusal without confirming the session exists.
    """
    return str(websocket.query_params.get("tenant_id") or "").strip()


@router.websocket("/v1/live/{session_id}")
async def live_websocket(websocket: WebSocket, session_id: str) -> None:
    """Refuse a live session without consent (IG-08) or approval (IG-10)."""
    tenant_id = _tenant_of(websocket)
    backend = getattr(websocket.app.state, "backend", None)
    events = getattr(websocket.app.state, "events", None)

    if not tenant_id:
        # Decided before accept, delivered after — finding 1.
        await websocket.accept()
        await websocket.close(
            code=CLOSE_UNAUTHORIZED, reason="A tenant is required to open a session."
        )
        return

    # IG-08 before IG-10, matching §5's own numbering — and the more
    # fundamental question first. Whether we may record this person at all is
    # not contingent on whether somebody approved a questionnaire.
    #
    # AC-3: this holds against a socket opened directly at /v1/live/{id},
    # bypassing the UI entirely. The browser's disabled record button is a
    # courtesy; this is the gate.
    consent = await fetch_consent_state(
        backend, tenant_id=tenant_id, session_id=session_id
    )
    consent_refusal = consent_verdict(consent)
    if consent_refusal.blocked:
        await emit_refusal(
            events, consent_refusal, tenant_id=tenant_id, session_id=session_id
        )
        await websocket.accept()
        await websocket.close(code=CLOSE_FORBIDDEN, reason=consent_refusal.detail[:120])
        return

    verdict = await evaluate(backend, tenant_id=tenant_id, session_id=session_id)

    await websocket.accept()
    if verdict.refused:
        # close() reason is capped at 123 bytes by the protocol; a longer one
        # is silently dropped by some clients, which would turn a helpful
        # refusal into a bare code.
        await websocket.close(code=verdict.close_code, reason=verdict.reason[:120])
        return

    # The gate passed. F-04 takes over from here; until it lands there is no
    # protocol to run, and holding an accepted socket open with nothing behind
    # it would look like a working meeting.
    await websocket.close(
        code=1001,
        reason="Live streaming is not available yet (F-04).",
    )
