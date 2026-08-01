"""WebSocket endpoint for LIVE mode — WS /v1/live/{session_id}.

Design §10.2.3, §4.3 · implemented by story F-04.

Scaffolded by A-05. The body raises NotImplementedError deliberately: a
stub that silently returns None would let a later story ship a no-op
that passes its tests.
"""

from __future__ import annotations

_NOT_YET = (
    "WebSocket endpoint for LIVE mode — WS /v1/live/{session_id}. — implemented by F-04"
)


async def live_websocket(*args: object, **kwargs: object) -> None:
    """Not yet implemented.

    Spike A-02 established three constraints this endpoint must honour: a close
    code cannot be delivered before accept(); the JWT arrives as a ?jwt= query
    parameter because browsers cannot set headers on a WS handshake; and
    session state must live in Redis because sockets land on different Cloud
    Run instances. See docs/spikes/A-02-gateway-websocket-note.md.
    """
    raise NotImplementedError(_NOT_YET)
