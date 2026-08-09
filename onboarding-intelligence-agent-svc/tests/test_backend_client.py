"""C-02 PR 3 · the agent's write to Django.

A real ``httpx.AsyncClient`` against a real local HTTP server. The property
worth proving is the one a mock cannot: **no failure here reaches the
operator**, because the brief is already in the response and in Redis by the
time this runs, and a durable-copy problem must not cost someone their turn.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.services.backend_client import BackendClient

pytestmark = pytest.mark.integration


def breaker(**overrides) -> CircuitBreaker:
    base = dict(
        name="backend",
        failure_threshold=5,
        window_seconds=30,
        success_threshold=2,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="REDIS_OUTBOX",
        user_message="Saving is delayed.",
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


@pytest.fixture
def django_stub():
    state = {"status": 201, "body": {"stored": True, "created": True}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            state["requests"].append(
                {
                    "path": self.path,
                    "token": self.headers.get("X-Service-Token"),
                    "tenant": self.headers.get("X-Tenant-ID"),
                    "body": json.loads(raw or b"{}"),
                }
            )
            payload = json.dumps(state["body"]).encode()
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


def good_brief(**overrides):
    brief = {
        "company_name": "Kalyani Roasters",
        "facts": [{"statement": "Founded 2016.", "source_url": "https://k.example/a"}],
        "open_unknowns": ["What is their AOV?"],
        "degraded": False,
    }
    brief.update(overrides)
    return brief


# ── The happy path ───────────────────────────────────────────────────


async def test_a_brief_is_posted_with_the_service_token(django_stub):
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    stored = await client.store_research_brief(
        tenant_id="t-1", company_name="Kalyani Roasters", brief=good_brief()
    )

    assert stored is True
    sent = django_stub["requests"][0]
    assert sent["path"] == "/api/v1/onboarding/research-briefs/upsert/"
    assert sent["token"] == "tok"
    assert sent["body"]["company_name"] == "Kalyani Roasters"


async def test_a_session_id_is_included_when_there_is_one(django_stub):
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    await client.store_research_brief(
        tenant_id="t-1", company_name="Kalyani", brief=good_brief(), session_id="sess-1"
    )

    assert django_stub["requests"][0]["body"]["session_id"] == "sess-1"


async def test_no_session_id_is_sent_when_there_is_none(django_stub):
    """Prep precedes the session; sending a null would make Django decide what
    an explicit null means."""
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    await client.store_research_brief(
        tenant_id="t-1", company_name="Kalyani", brief=good_brief()
    )

    assert "session_id" not in django_stub["requests"][0]["body"]


# ── Nothing here may cost the operator their turn ────────────────────


@pytest.mark.parametrize("status", [400, 403, 500, 503])
async def test_an_error_response_is_swallowed(django_stub, status):
    django_stub["status"] = status
    django_stub["body"] = {"error": "no"}
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    stored = await client.store_research_brief(
        tenant_id="t-1", company_name="Kalyani", brief=good_brief()
    )

    assert stored is False, "a storage failure must not raise"


async def test_an_unreachable_backend_is_swallowed():
    """A genuinely closed port, not a simulated outage."""
    client = BackendClient("http://127.0.0.1:1", "tok", breaker=breaker())

    assert (
        await client.store_research_brief(
            tenant_id="t-1", company_name="K", brief=good_brief()
        )
        is False
    )


async def test_a_non_json_response_is_swallowed(django_stub):
    django_stub["body"] = "<html>gateway</html>"
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    assert (
        await client.store_research_brief(
            tenant_id="t-1", company_name="K", brief=good_brief()
        )
        is False
    )


async def test_failures_open_the_breaker(django_stub):
    """So a backend outage stops costing a round trip on every turn."""
    django_stub["status"] = 500
    brk = breaker(failure_threshold=2)
    client = BackendClient(django_stub["url"], "tok", breaker=brk)

    await client.store_research_brief(
        tenant_id="t-1", company_name="K", brief=good_brief()
    )
    await client.store_research_brief(
        tenant_id="t-1", company_name="K", brief=good_brief()
    )

    assert brk.state is State.OPEN


async def test_an_open_breaker_does_not_call_out(django_stub):
    brk = breaker(failure_threshold=1)
    brk.record_failure()
    client = BackendClient(django_stub["url"], "tok", breaker=brk)

    await client.store_research_brief(
        tenant_id="t-1", company_name="K", brief=good_brief()
    )

    assert django_stub["requests"] == []


# ── The PLACEHOLDER case ─────────────────────────────────────────────


@pytest.mark.unit
async def test_a_placeholder_base_url_is_treated_as_unconfigured():
    """Until C-02 added OIA to 10-redeploy-with-urls.sh, the deployed service
    held the literal string "PLACEHOLDER" as its backend URL.

    Treating that as a hostname means every write fails DNS and opens the
    breaker, which reports an outage when the truth is a missing deploy step —
    and sends whoever is on call to the wrong system.
    """
    brk = breaker(failure_threshold=1)
    client = BackendClient("PLACEHOLDER", "tok", breaker=brk)

    assert client.configured is False
    assert (
        await client.store_research_brief(
            tenant_id="t-1", company_name="K", brief=good_brief()
        )
        is False
    )
    assert brk.state is State.CLOSED, "a config gap was reported as an outage"


@pytest.mark.unit
async def test_an_empty_base_url_is_treated_as_unconfigured():
    client = BackendClient("", "tok", breaker=breaker())

    assert client.configured is False


# ── A degraded brief is not even sent ────────────────────────────────


@pytest.mark.integration
async def test_a_degraded_brief_is_not_sent(django_stub):
    """Django refuses it anyway — the rule is enforced on both sides
    deliberately — but spending a round trip to be told no is wasteful on the
    exact path where the dependency may already be unwell."""
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    stored = await client.store_research_brief(
        tenant_id="t-1",
        company_name="K",
        brief=good_brief(degraded=True, degraded_reason="tavily breaker open"),
    )

    assert stored is False
    assert django_stub["requests"] == []


async def test_the_tenant_is_sent_as_a_header(django_stub):
    """Django cannot infer it. DefaultTenantMiddleware resolves an unmatched
    host — always, for an internal call — to the *public* tenant, so a write
    with no header is attributed to the wrong tenant rather than rejected.
    The agent is the only party that knows which tenant it is acting for.
    """
    client = BackendClient(django_stub["url"], "tok", breaker=breaker())

    await client.store_research_brief(
        tenant_id="tenant-42", company_name="Kalyani", brief=good_brief()
    )

    assert django_stub["requests"][0]["tenant"] == "tenant-42"


@pytest.mark.unit
def test_two_clients_do_not_share_a_breaker():
    """The property that makes sharing one client necessary.

    Each BackendClient builds its own BreakerRegistry, so two of them hold
    independent state for the same dependency. This is not a bug in the client
    — a caller may legitimately want an isolated breaker — but it is why the
    app must construct exactly one and hand it to everything.
    """
    first = BackendClient("http://x", "tok")
    second = BackendClient("http://x", "tok")

    for _ in range(5):
        first._breaker.record_failure()

    assert first._breaker is not second._breaker
    assert first._breaker.is_open is True
    assert second._breaker.is_open is False


@pytest.mark.unit
def test_the_app_shares_one_backend_client_across_prep_and_the_gate():
    """Review finding, asserted on the wiring rather than trusted to a comment.

    Two clients meant Django could be failing for the PREP path and "healthy"
    for the IG-10 gate, with the gate paying a full timeout per socket after
    PREP had already given up. The comment in main.py claimed they shared one
    while the code created two.
    """
    import inspect

    import app.main as main

    source = inspect.getsource(main)
    assert source.count("BackendClient(") == 1, (
        "main.py constructs more than one BackendClient; the PREP path and "
        "the IG-10 gate would hold independent breakers"
    )
    assert "backend=app.state.backend" in source
