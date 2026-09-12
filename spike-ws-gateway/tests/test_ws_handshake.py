"""Stub committed by spike A-02 for story F-04 to inherit.

The backlog's test-case table for A-02 lists exactly one production test file:
``tests/test_ws_handshake.py``, "stub committed, skipped", proving "F-04
inherits a file rather than creating one".

**Handoff.** A-05 scaffolds ``onboarding-intelligence-agent-svc/``. Move this
file to ``onboarding-intelligence-agent-svc/tests/test_ws_handshake.py``, drop
the skip marker, and point the imports at ``app.api.ws`` /
``app.logic.live_session``. The spike's ``echo/`` package is the reference
implementation for every behaviour asserted below — each one is already proven
against a real socket in ``test_echo_integration.py`` and, through a real
gateway, in ``test_kong_ws_integration.py``.

Two findings from the spike that F-04 must honour and that these stubs encode:

1. A close code cannot be delivered before ``accept()``. Starlette answers a
   pre-accept close with plain HTTP 403 and the client never sees 4401. The
   authorisation *decision* still belongs before accept; only the delivery of
   the verdict happens after it. See ``echo.main._reject``.
2. The JWT arrives as a query parameter, not a header — browsers cannot set
   headers on a WebSocket handshake. See ``echo.auth``.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="A-02 spike stub — F-04 implements these against app/api/ws.py"
)


def test_close_codes_map_one_to_one():
    """Each handshake failure maps to its own §10.2.3 close code.

    4401 invalid or expired JWT, 4403 consent missing or revoked (IG-08),
    4404 session not found or not live-eligible, 4409 another socket already
    live, 4429 rate limited.
    """


def test_second_socket_rejected_4409():
    """One live socket per session: the newcomer loses, the incumbent does not.

    F-04 additionally holds the lock in Redis with a TTL so a crashed process
    cannot lock a session out permanently — ERRATA-01 puts that lock in DB 2
    under the ``oia:v1:`` prefix, not DB 27.
    """


def test_handshake_authorises_before_accept():
    """JWT, tenant, role (Owner/Admin/Editor), consent and session state.

    All five are evaluated before the socket is accepted; see finding (1) in
    the module docstring for how the verdict is then delivered.
    """


def test_jwt_arrives_as_query_parameter():
    """The token carrier is ``?jwt=``, matching Kong's uri_param_names."""


def test_tenantless_token_is_rejected():
    """A socket that opens but arrives tenant-less is a failure, not a pass."""
