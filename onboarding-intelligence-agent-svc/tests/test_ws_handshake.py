"""C-04 AC-4 · the IG-10 gate on the live socket.

The card names ``test_draft_questionnaire_rejected_4403`` here. Driven through
a real ``TestClient`` WebSocket rather than by calling the endpoint function,
because the thing worth proving is that the *client* sees the code — and spike
A-02's first finding is precisely that a close made at the wrong moment reaches
the client as plain HTTP 403 with no code at all. Only a real handshake shows
the difference.

Django stands in as a local HTTP server. Its answer is the whole input to the
decision, so controlling it is controlling the test.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.logic.live_gate import CLOSE_FORBIDDEN, UNREACHABLE_REASON, evaluate
from app.services.backend_client import BackendClient

pytestmark = pytest.mark.integration

CLOSE_UNAUTHORIZED = 4401


@pytest.fixture
def django_stub():
    """A local stand-in for Django's live-precheck endpoint."""
    # Consent present and active by default, so the IG-10 cases below keep
    # testing IG-10. F-01 put IG-08 ahead of it in the same handler, and a
    # stub that omitted consent would refuse every socket before the
    # questionnaire was ever considered — turning this file green for the
    # wrong reason on the approved-questionnaire case and red on the rest.
    state = {
        "status": 200,
        "body": {
            "approved": True,
            "consent": {"present": True, "active": True, "consent_id": "c-1"},
        },
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(
                {"path": self.path, "tenant": self.headers.get("X-Tenant-ID")}
            )
            # Consent defaults to present-and-active unless a test says
            # otherwise. F-01 put IG-08 ahead of IG-10 in the same handler, so
            # without this every test here would be refused for consent before
            # its questionnaire was ever looked at — and the IG-10 cases would
            # be passing on the wrong refusal. A test about consent sets the
            # block explicitly and this leaves it alone.
            body = dict(state["body"])
            if not state.get("omit_consent_default"):
                body.setdefault(
                    "consent", {"present": True, "active": True, "consent_id": "c-1"}
                )
            payload = json.dumps(body).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def client(app_with_live_redis, django_stub):
    with TestClient(app_with_live_redis) as test_client:
        app_with_live_redis.state.backend = BackendClient(django_stub["url"], "tok")
        yield test_client


def open_socket(client, session_id="sess-1", tenant_id="t-1"):
    query = f"?tenant_id={tenant_id}" if tenant_id is not None else ""
    return client.websocket_connect(f"/v1/live/{session_id}{query}")


# ── The card's named case ────────────────────────────────────────────


def test_draft_questionnaire_rejected_4403(client, django_stub):
    """The card's case. A DRAFT questionnaire must not start a meeting."""
    django_stub["body"] = {
        "approved": False,
        "questionnaire_status": "DRAFT",
        "reason": "Questionnaire 12 is DRAFT. Approve it in preparation "
        "before starting the meeting.",
    }

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == CLOSE_FORBIDDEN


def test_the_refusal_names_the_missing_approval(client, django_stub):
    """AC-4: "a message naming the missing approval".

    An operator told only "forbidden" retries the same thing. One told which
    questionnaire and what state it is in goes and fixes it.
    """
    django_stub["body"] = {
        "approved": False,
        "questionnaire_status": "DRAFT",
        "reason": "Questionnaire 12 is DRAFT. Approve it in preparation.",
    }

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert "Questionnaire 12" in caught.value.reason
    assert "Approve" in caught.value.reason


def test_the_client_receives_a_code_not_an_http_403(client, django_stub):
    """Spike A-02's first finding, asserted rather than trusted.

    Closing a Starlette socket before accept() makes the framework answer the
    handshake with plain HTTP 403 and the code never arrives. If this endpoint
    ever regresses to a pre-accept close, the connect itself would raise
    instead of yielding a socket that then disconnects with 4403 — which is
    what this distinguishes.
    """
    django_stub["body"] = {"approved": False, "reason": "not approved"}

    socket = open_socket(client)
    with socket as connected:
        with pytest.raises(WebSocketDisconnect) as caught:
            connected.receive_text()

    assert caught.value.code == CLOSE_FORBIDDEN, (
        "the client got no application close code — the verdict is being "
        "delivered before accept()"
    )


# ── Failing closed ───────────────────────────────────────────────────


def test_an_unreachable_backend_refuses(client, django_stub):
    """§5: the guardrails "fail closed on any".

    A false refusal costs one retry. A false permit puts a meeting on air
    against a questionnaire nobody approved, and cannot be walked back once
    the brand owner has started answering.
    """
    django_stub["status"] = 500
    django_stub["body"] = {"error": "boom"}

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == CLOSE_FORBIDDEN


def test_a_session_outside_the_tenant_refuses(client, django_stub):
    """Django answers 404 for a session in another tenant — FR-PREP-06 is
    explicit that a cross-tenant read must not confirm the row exists. The
    gate turns that into a refusal without leaking whether it does."""
    django_stub["status"] = 404
    django_stub["body"] = {"error": "session not found"}

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == CLOSE_FORBIDDEN


def test_no_tenant_is_refused_before_any_backend_call(client, django_stub):
    with open_socket(client, tenant_id="") as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == CLOSE_UNAUTHORIZED
    assert django_stub["requests"] == []


# ── The allowed path ─────────────────────────────────────────────────


def test_an_approved_questionnaire_passes_the_gate(client, django_stub):
    """The control. A gate that refused everything would pass every test
    above while making the feature impossible.

    It still closes — F-04 owns the protocol — but with 1001 (going away)
    rather than 4403, and the reason says why.
    """
    django_stub["body"] = {"approved": True, "questionnaire_status": "APPROVED"}

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == 1001
    assert "F-04" in caught.value.reason


def test_the_tenant_is_sent_to_django(client, django_stub):
    django_stub["body"] = {"approved": True}

    with open_socket(client, tenant_id="tenant-42") as socket:
        with pytest.raises(WebSocketDisconnect):
            socket.receive_text()

    assert django_stub["requests"][0]["tenant"] == "tenant-42"
    assert "/sessions/sess-1/live-precheck/" in django_stub["requests"][0]["path"]


# ── The verdict, without a socket ────────────────────────────────────


@pytest.mark.unit
async def test_a_missing_backend_fails_closed():
    """Decided in live_gate, not in the endpoint, so it is testable without a
    socket — which is why the decision lives there."""
    verdict = await evaluate(None, tenant_id="t-1", session_id="s-1")

    assert verdict.refused is True
    assert verdict.reason == UNREACHABLE_REASON
    assert verdict.close_code == CLOSE_FORBIDDEN


# ── F-01 AC-3 · the consent gate, ahead of IG-10 ─────────────────────


def test_close_4403_on_missing_consent(client, django_stub):
    """The card's named case.

    AC-3: a socket opened directly at /v1/live/{id}, bypassing the UI, is
    refused server-side. The browser's disabled record button is a courtesy;
    this is the gate — and this test is the only thing that proves the two are
    not the same claim.
    """
    django_stub["body"] = {
        "approved": True,
        "consent": {"present": False, "active": False},
    }

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client) as socket:
            socket.receive_text()

    assert caught.value.code == 4403
    assert "consent_required" in caught.value.reason


def test_close_4403_on_revoked_consent(client, django_stub):
    """A record that exists is not consent. `revoked_at` being set means the
    brand owner withdrew it, and a gate that only checked existence would keep
    a meeting on air for someone who asked us to stop."""
    django_stub["body"] = {
        "approved": True,
        "consent": {"present": True, "active": False, "consent_id": "c-9"},
    }

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client) as socket:
            socket.receive_text()

    assert caught.value.code == 4403
    assert "revoked" in caught.value.reason


def test_consent_is_checked_before_the_questionnaire(client, django_stub):
    """Ordering is observable, so it is asserted.

    §5 numbers IG-08 before IG-10, and the question "may we record this
    person at all" does not depend on whether somebody approved a
    questionnaire. With both failing, the operator should be told the one that
    matters first.
    """
    django_stub["body"] = {
        "approved": False,
        "reason": "Questionnaire 12 is still DRAFT.",
        "consent": {"present": False, "active": False},
    }

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client) as socket:
            socket.receive_text()

    assert caught.value.code == 4403
    assert "consent_required" in caught.value.reason
    assert "Questionnaire" not in caught.value.reason


def test_a_backend_that_omits_consent_is_refused(client, django_stub):
    """A Django too old to report consent must not be read as consent given.

    The deploy order is agent-then-backend as often as not, and a gate that
    treated a missing block as "fine" would be switched off by a version skew
    that nobody chose and nothing reports.
    """
    django_stub["body"] = {"approved": True}  # no consent key at all
    django_stub["omit_consent_default"] = True

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client) as socket:
            socket.receive_text()

    assert caught.value.code == 4403


def test_the_refusal_never_carries_the_subject_name(client, django_stub):
    """A close reason reaches browser consoles and gateway logs. The subject's
    name belongs in the ConsentRecord and nowhere else."""
    django_stub["body"] = {
        "approved": True,
        "consent": {
            "present": True,
            "active": False,
            "consent_id": "c-9",
            "subject_name": "Ada Lovelace",
        },
    }

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client) as socket:
            socket.receive_text()

    assert "Ada" not in caught.value.reason
    assert "Lovelace" not in caught.value.reason
