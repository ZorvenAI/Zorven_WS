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

import hashlib
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
CLOSE_NOT_FOUND = 4404
CLOSE_INTERNAL = 1011


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
            if not state.get("omit_auth_default"):
                # F-04 put ticket authorisation ahead of everything else. A
                # stub that omitted it would refuse every socket with 4401 and
                # the IG-08/IG-10 cases below would be passing on the wrong
                # refusal — the same trap the consent default was added for.
                body.setdefault(
                    "auth",
                    {
                        "valid": True,
                        "tenant_id": "t-1",
                        "company_id": state.get("company_id", "c-1"),
                        "user_id": "u-1",
                        "role": "editor",
                        "valid_until": "2099-01-01T00:00:00+00:00",
                    },
                )
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
        t = threading.Thread(target=server.shutdown, daemon=True)
        t.start()
        t.join(timeout=5)
        server.server_close()


@pytest.fixture
def live_company(request):
    """A company id unique to each test.

    F-04's single-socket lock is keyed on company and lives in Redis, which
    outlives a test. Sharing one id made every case after the first contend
    with a lock the previous one had left behind — a suite that hung rather
    than failed, and for a reason that had nothing to do with what was being
    tested.
    """
    return f"c-{hashlib.md5(request.node.name.encode()).hexdigest()[:8]}"


@pytest.fixture
def client(app_with_live_redis, django_stub, live_company):
    with TestClient(app_with_live_redis) as test_client:
        app_with_live_redis.state.backend = BackendClient(django_stub["url"], "tok")
        # F-04 holds the socket open and re-checks on a cadence. The real one
        # is thirty seconds; a suite that waited that out per case would not
        # be run.
        app_with_live_redis.state.live_poll_s = 0.05
        django_stub["company_id"] = live_company
        # No explicit lock cleanup: the per-test company id above is what
        # isolates these, and a teardown that drove the event loop by hand
        # errored inside the running one — cleanup that breaks the tests it
        # protects is worse than the leak it was guarding against.
        yield test_client


def expect_close(socket, within: float = 10.0) -> WebSocketDisconnect:
    """Wait for the server to close, and fail rather than hang if it does not.

    Starlette's test client has no receive timeout, so the obvious
    `pytest.raises(WebSocketDisconnect): socket.receive_text()` blocks for ever
    when the close it expects never comes. That is how a mutation to the lock
    or the expiry check turns into a six-hour CI job instead of a red test —
    observed while checking exactly those two guards.

    The default timeout is 10s rather than 3s: on a loaded CI runner the poll
    loop in _hold needs multiple cycles (each doing Redis + HTTP) before it
    sees the consent change, and a tight window turns a slow runner into a
    deadlock — Starlette's TestClient __exit__ does an indefinite
    Condition.wait() to join the ASGI thread, so if this helper times out
    before the server closes, the 300s pytest-timeout fires instead.
    """
    import threading

    caught: list[BaseException] = []

    def wait():
        try:
            socket.receive_text()
        except BaseException as error:  # noqa: BLE001 - reported below
            caught.append(error)

    thread = threading.Thread(target=wait, daemon=True)
    thread.start()
    thread.join(timeout=within)

    assert caught, f"the socket was still open after {within}s — expected a close"
    error = caught[0]
    # Raised rather than asserted: this is the helper's precondition, not a
    # test's conclusion, and `assert isinstance(...)` as the last word of a
    # check is the shape the weak-assertion gate exists to catch. The
    # conclusions are the code below and the values at each call site.
    if not isinstance(error, WebSocketDisconnect):
        raise AssertionError(f"unexpected {type(error).__name__}: {error}")
    # A value, not just a type. Spike A-02's first finding is that a close made
    # before accept() reaches the client with *no* application code — the
    # disconnect still arrives, so a type check alone would pass on exactly the
    # regression this file exists to catch.
    assert error.code, "the close carried no application close code"
    return error


def open_socket(client, session_id="sess-1", tenant_id="t-1", ticket="tkt-1"):
    parts = []
    if tenant_id is not None:
        parts.append(f"tenant_id={tenant_id}")
    if ticket is not None:
        parts.append(f"ticket={ticket}")
    query = ("?" + "&".join(parts)) if parts else ""
    return client.websocket_connect(f"/v1/live/{session_id}{query}")


# ── The card's named case ────────────────────────────────────────────


def test_draft_questionnaire_rejected_4404(client, django_stub):
    """C-04's case, with F-04's close code.

    C-04 closed this 4403. §10.2.3 gives 4403 to "consent missing or revoked"
    and 4404 to "session not found or **not live-eligible**", and a draft
    questionnaire is the second. F-04's AC-1 makes the mapping one-to-one and
    `test_close_codes_map_one_to_one` asserts it, so the overlap had to go —
    a client that cannot tell an eligibility problem from a consent problem
    re-presents the consent modal for a questionnaire nobody approved.
    """
    django_stub["body"] = {
        "approved": False,
        "questionnaire_status": "DRAFT",
        "reason": "Questionnaire 12 is DRAFT. Approve it in preparation "
        "before starting the meeting.",
    }

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == CLOSE_NOT_FOUND


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
    instead of yielding a socket that then disconnects with a code — which is
    what this distinguishes.
    """
    django_stub["body"] = {"approved": False, "reason": "not approved"}

    socket = open_socket(client)
    with socket as connected:
        with pytest.raises(WebSocketDisconnect) as caught:
            connected.receive_text()

    assert caught.value.code == CLOSE_NOT_FOUND, (
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

    # 1011, not a 4xxx: an unreachable backend is *our* failure, and telling
    # the client its credentials are bad sends it to re-authenticate against
    # a problem that is not there.
    assert caught.value.code == CLOSE_INTERNAL


def test_a_session_outside_the_tenant_refuses(client, django_stub):
    """Django answers 404 for a session in another tenant — FR-PREP-06 is
    explicit that a cross-tenant read must not confirm the row exists. The
    gate turns that into a refusal without leaking whether it does."""
    django_stub["status"] = 404
    django_stub["body"] = {"error": "session not found"}

    with open_socket(client) as socket:
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_text()

    assert caught.value.code == CLOSE_NOT_FOUND


def test_the_caller_supplied_tenant_is_not_what_authorises(client, django_stub):
    """F-04 replaced a check this test used to assert.

    C-04 refused a socket with no `tenant_id` query parameter before calling
    Django at all, and said in its own docstring that reading identity from
    the query string was "**not** adequate for a socket that carries data".
    This is that socket. Identity now comes from the ticket Django resolved,
    so the query parameter is routing information, not a claim — and omitting
    it no longer decides anything.

    That is the property worth asserting: the socket is authorised on the
    ticket's tenant, not on whatever the caller typed.
    """
    with open_socket(client, tenant_id="") as socket:
        socket.send_text("authorised on the ticket, not the query string")

        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(socket)

    # The backend was consulted, which is the whole point — the old behaviour
    # refused without asking.
    assert django_stub["requests"], "the handshake never reached Django"


# ── The allowed path ─────────────────────────────────────────────────


def test_an_approved_questionnaire_holds_the_socket_open(client, django_stub):
    """The control. A gate that refused everything would pass every test above
    while making the feature impossible.

    C-04 closed here with 1001 because there was no protocol behind the gate
    and "holding an accepted socket open with nothing behind it would look
    like a working meeting". F-04 owns the lifecycle, so the socket now stays:
    the connection *is* what this story delivers, and the frames travelling
    over it arrive in PR 2.
    """
    django_stub["body"] = {"approved": True, "questionnaire_status": "APPROVED"}

    with open_socket(client) as socket:
        # Sending proves it is open. `receive_text()` would be the obvious
        # check and is the wrong one — Starlette's test client takes no
        # timeout, so it blocks for ever on a socket that is behaving
        # correctly, which is a hung suite rather than a failed assertion.
        socket.send_text("still here")

        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(socket)


def test_the_tenant_is_sent_to_django(client, django_stub):
    django_stub["body"] = {"approved": True}

    with open_socket(client, tenant_id="tenant-42") as socket:
        socket.send_text("open")

        # Trigger server-side close via consent revocation so _hold exits
        # cleanly (see test_second_socket_rejected_4409 for the rationale).
        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(socket)

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


# ── F-04 PR 1 · the card's named cases ───────────────────────────────


def test_close_codes_map_one_to_one():
    """§10.2.3's codes, each meaning one thing.

    NFR-SEC-02 asks for them "as named constants, not literals", and the
    reason is this test: a client that cannot tell an eligibility failure from
    a consent failure re-presents the consent modal for a questionnaire nobody
    approved. C-04 closed a draft questionnaire with 4403 — consent's code —
    and F-04 moves it to 4404, which is what makes the mapping injective.

    Six, not the five AC-1 lists: §10.2.3 also defines 1011 for an internal
    error with retry advised, and NFR-SEC-02 says "the six close codes".
    """
    from app.logic.live_handshake import CLOSE_CODES

    assert len(CLOSE_CODES) == 6
    assert len(set(CLOSE_CODES.values())) == 6, "two conditions share a code"
    assert CLOSE_CODES == {
        "unauthorized": 4401,
        "forbidden": 4403,
        "not_found": 4404,
        "conflict": 4409,
        "rate_limited": 4429,
        "internal": 1011,
    }


def test_second_socket_rejected_4409(client, django_stub):
    """AC-2, and the reason the lock is in Redis rather than in the process.

    Spike A-02 finding 3: sockets for one tenant land on different Cloud Run
    instances, so a process-local flag would admit one socket per instance and
    call that exclusivity. Two writers on one meeting corrupt the transcript
    for both.
    """
    django_stub["body"] = {"approved": True}

    with open_socket(client) as first:
        first.send_text("holding the slot")

        with open_socket(client) as second:
            closed = expect_close(second)

        assert closed.code == 4409
        # AC-2: "the first is untouched". A guard that closed both would
        # satisfy "only one socket" and lose the meeting.
        first.send_text("still holding")

        # _hold re-checks consent every poll tick. Revoking it here makes
        # the handler close the socket itself, preventing a deadlock
        # between Starlette's TestClient cleanup and the in-flight HTTP
        # calls _hold makes during its consent loop.
        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(first)


def test_the_first_socket_releases_its_claim_when_it_ends(client, django_stub):
    """The control. A lock never released is a company locked out of its own
    meetings until the TTL lapses, and the operator's remedy is a support
    ticket."""
    django_stub["body"] = {"approved": True}

    with open_socket(client) as first:
        first.send_text("one")

        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(first)

    django_stub["body"] = {"approved": True}

    with open_socket(client) as second:
        second.send_text("two")

        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(second)


def test_live_keys_are_tenant_scoped():
    """The card's named case, asserted on the builder rather than on a socket.

    Every key this service writes starts with `oia:v1:` and carries the tenant
    — the shared Memorystore instance is DB 2 for eleven services, and prefix
    isolation is the only thing separating them (ERRATA-01).
    """
    # The builder directly: it is pure, and reaching it through app.state
    # made this depend on a connected Redis for a question about string
    # construction.
    from app.cache.redis_manager import TenantKeys

    key = TenantKeys("tenant-abc").live_lock("company-xyz")

    assert key.startswith("oia:v1:tenant-abc:")
    assert "company-xyz" in key


def test_an_expired_authorisation_closes_an_idle_socket(client, django_stub):
    """NFR-SEC-02: "a token that expires mid-session closes the socket with
    4401, **not at the next message boundary**".

    Idle is the case that matters — a meeting where nobody is speaking still
    holds a connection, and a check that only runs on traffic never runs.
    """
    django_stub["body"] = {
        "approved": True,
        "auth": {
            "valid": True,
            "tenant_id": "t-1",
            "company_id": django_stub.get("company_id", "c-1"),
            "user_id": "u-1",
            "role": "editor",
            # Already past.
            "valid_until": "2020-01-01T00:00:00+00:00",
        },
    }

    with open_socket(client) as socket:
        closed = expect_close(socket)

    assert closed.code == CLOSE_UNAUTHORIZED
    assert "expired" in closed.reason.lower()


def test_a_viewer_cannot_open_a_live_socket(client, django_stub):
    """§15: a Viewer reads a session and does not run a meeting. 4403 rather
    than 4401 — they are who they say they are, and the answer is still no, so
    re-authenticating would not help."""
    django_stub["body"] = {
        "approved": True,
        "auth": {
            "valid": True,
            "tenant_id": "t-1",
            "company_id": django_stub.get("company_id", "c-1"),
            "user_id": "u-9",
            "role": "viewer",
            "valid_until": "2099-01-01T00:00:00+00:00",
        },
    }

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client) as socket:
            socket.receive_text()

    assert caught.value.code == CLOSE_FORBIDDEN
    assert "viewer" in caught.value.reason.lower()


def test_an_invalid_ticket_is_4401(client, django_stub):
    django_stub["body"] = {"approved": True, "auth": {"valid": False, "reason": "x"}}

    with pytest.raises(WebSocketDisconnect) as caught:
        with open_socket(client, ticket="nonsense") as socket:
            socket.receive_text()

    assert caught.value.code == CLOSE_UNAUTHORIZED


# ── F-04 PR 2 · resume over a real socket ────────────────────────────


def test_a_resume_replays_the_frames_the_client_missed(client, django_stub):
    """AC-3 end to end, over a real handshake.

    The unit tests cover the buffer's arithmetic; this covers the thing a
    client experiences — that sending `{"type": "resume", "last_seq": N}`
    brings back exactly what it missed, in order.
    """
    import uuid

    import redis as sync_redis

    from app.api.schemas import TranscriptPartial
    from app.cache.redis_manager import TenantKeys
    from tests.conftest import REDIS_URL

    session_id = f"sess-replay-{uuid.uuid4().hex[:8]}"
    django_stub["body"] = {"approved": True}

    r = sync_redis.Redis.from_url(REDIS_URL)
    keys = TenantKeys("t-1")
    seq_key = keys.live_seq(session_id)
    frames_key = keys.live_frames(session_id)
    try:
        for index in range(1, 5):
            seq = r.incr(seq_key)
            frame = TranscriptPartial(seq=seq, text=f"chunk {index}", speaker=2)
            r.rpush(frames_key, json.dumps(frame.model_dump(mode="json")))
    finally:
        r.close()

    with open_socket(client, session_id=session_id) as socket:
        socket.send_json({"type": "resume", "last_seq": 2})

        first = socket.receive_json()
        second = socket.receive_json()

        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(socket)

    assert first["seq"] < second["seq"], "frames replayed out of order"
    assert first["text"] == "chunk 3"
    assert second["text"] == "chunk 4"


def test_a_resume_beyond_the_buffer_gets_a_resync_frame(client, django_stub):
    """AC-3: "not a silent gap in seq". The client is told the record moved on
    rather than left to infer it from frames that never arrive."""
    import uuid

    session_id = f"sess-resync-{uuid.uuid4().hex[:8]}"
    django_stub["body"] = {"approved": True}

    with open_socket(client, session_id=session_id) as socket:
        socket.send_json({"type": "resume", "last_seq": 900})
        answer = socket.receive_json()

        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(socket)

    assert answer["type"] == "resync"
    assert "from_seq" in answer


def test_a_malformed_control_frame_does_not_end_the_meeting(client, django_stub):
    """A client bug must not close a socket that is otherwise recording
    fine — the audio path does not depend on the control channel being
    well-formed."""
    import uuid

    session_id = f"sess-malform-{uuid.uuid4().hex[:8]}"
    django_stub["body"] = {"approved": True}

    with open_socket(client, session_id=session_id) as socket:
        socket.send_text("{not json")
        socket.send_json({"type": "resume"})  # missing last_seq
        # Still open: sending again would raise if the server had closed.
        socket.send_text("still here")

        # Trigger server-side close via consent revocation so _hold exits
        # cleanly (see test_second_socket_rejected_4409 for the rationale).
        django_stub["body"]["consent"] = {
            "present": True,
            "active": False,
            "consent_id": "c-1",
        }
        expect_close(socket)
