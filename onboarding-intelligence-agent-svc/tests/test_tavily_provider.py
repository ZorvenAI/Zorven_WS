"""C-02 · the Tavily provider and its breaker wiring.

No mocks. ``AsyncTavilyClient`` takes an ``api_base_url``, so these run the
**real** client library against a local HTTP server whose responses the test
controls. That matters more than it sounds: a mocked client proves the code
handles the response shape the test author imagined, whereas this proves it
handles what the library actually produces after its own parsing, error
handling and retries.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.providers.tavily import (
    SearchResult,
    TavilyProvider,
    TavilyUnavailable,
)

pytestmark = pytest.mark.integration


def breaker(**overrides) -> CircuitBreaker:
    base = dict(
        name="tavily",
        failure_threshold=3,
        window_seconds=60,
        success_threshold=1,
        half_open_max_calls=1,
        reset_timeout_seconds=60,
        degraded_mode="SKIP_RESEARCH",
        user_message=(
            "Web research unavailable — questionnaire generated from "
            "what you provided."
        ),
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


@pytest.fixture
def fake_tavily():
    """A real HTTP server the real Tavily client talks to.

    ``state`` is mutable so a test can change the response between calls —
    which is how the breaker's open-then-recover path gets exercised without
    anyone patching anything.
    """
    state = {
        "status": 200,
        "body": {"results": []},
        "content_type": "application/json",
        "requests": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state["requests"] += 1
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            body = state["body"]
            payload = (
                body.encode() if isinstance(body, str) else json.dumps(body).encode()
            )
            self.send_response(state["status"])
            self.send_header("Content-Type", state["content_type"])
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


def provider_for(fake, brk=None) -> TavilyProvider:
    from tavily import AsyncTavilyClient

    client = AsyncTavilyClient(api_key="test-key", api_base_url=fake["url"])
    return TavilyProvider("test-key", breaker=brk or breaker(), client=client)


# ── The happy path ───────────────────────────────────────────────────


async def test_results_are_parsed(fake_tavily):
    fake_tavily["body"] = {
        "results": [
            {
                "title": "Kalyani Roasters",
                "url": "https://kalyani.example/about",
                "content": "A speciality coffee roaster in Pune since 2016.",
            }
        ]
    }

    results = await provider_for(fake_tavily).search("Kalyani Roasters Pune")

    assert results == [
        SearchResult(
            title="Kalyani Roasters",
            url="https://kalyani.example/about",
            snippet="A speciality coffee roaster in Pune since 2016.",
        )
    ]


async def test_a_result_without_a_url_is_dropped(fake_tavily):
    """AC-1 requires a source URL per fact. A result that cannot ground
    anything is dropped here rather than carried forward to fail OG-01."""
    fake_tavily["body"] = {
        "results": [
            {"title": "no source", "content": "unattributable"},
            {"title": "sourced", "url": "https://x.example", "content": "ok"},
        ]
    }

    results = await provider_for(fake_tavily).search("q")

    assert [r.url for r in results] == ["https://x.example"]


async def test_finding_nothing_is_not_a_failure(fake_tavily):
    """An empty result set means "we looked and there is nothing", which is
    different from "we could not look" — the caller degrades only on the
    latter."""
    fake_tavily["body"] = {"results": []}
    brk = breaker()

    assert await provider_for(fake_tavily, brk).search("q") == []
    assert brk.state is State.CLOSED, "an empty result set tripped the breaker"


@pytest.mark.parametrize("body", [{"results": "not-a-list"}, {}])
async def test_an_odd_but_returnable_shape_yields_no_results(fake_tavily, body):
    """Shapes the client hands back rather than raising on.

    Verified against the real library rather than assumed: an empty object is
    normalised by the client to ``{"results": []}``, and a non-list ``results``
    is passed straight through for us to reject.
    """
    fake_tavily["body"] = body

    assert await provider_for(fake_tavily).search("q") == []


@pytest.mark.parametrize("body", [[1, 2, 3], "text"])
async def test_a_malformed_upstream_body_degrades_and_counts(fake_tavily, body):
    """These make the *client library itself* raise.

    A bare JSON list raises ``AttributeError: 'list' object has no attribute
    'get'`` from inside tavily-python — the same bug C-01's review found in our
    own dispatcher, here in a third-party package we do not control. A body
    that is not JSON at all raises JSONDecodeError. Both mean the call did not
    work, so both must become TavilyUnavailable and reach the breaker rather
    than escaping into the operator's chat turn.

    This is the evidence for the deliberately broad ``except Exception`` in the
    provider: the set of things this library can raise is not enumerable from
    its signature.
    """
    fake_tavily["body"] = body
    brk = breaker(failure_threshold=1)

    with pytest.raises(TavilyUnavailable):
        await provider_for(fake_tavily, brk).search("q")

    assert brk.is_open is True


@pytest.mark.unit
def test_parse_rejects_a_non_object_response():
    """Defence in depth for a path the current client version cannot produce —
    it raises on a bare list before we ever see one. Kept because the guard is
    free and the library's behaviour here is not part of its contract.
    """
    assert TavilyProvider._parse([1, 2, 3]) == []
    assert TavilyProvider._parse("text") == []
    assert TavilyProvider._parse(None) == []


# ── Failure reaches the breaker (AC-3's foundation) ──────────────────


async def test_a_server_error_raises_and_counts(fake_tavily):
    """The fleet's existing Tavily code returns [] here, which is
    indistinguishable from "nothing found". AC-3 needs the difference."""
    fake_tavily["status"] = 500
    fake_tavily["body"] = {"detail": "boom"}
    brk = breaker(failure_threshold=1)

    with pytest.raises(TavilyUnavailable):
        await provider_for(fake_tavily, brk).search("q")

    assert brk.is_open is True


async def test_repeated_failures_open_the_breaker(fake_tavily):
    fake_tavily["status"] = 500
    brk = breaker(failure_threshold=3)
    provider = provider_for(fake_tavily, brk)

    for _ in range(3):
        with pytest.raises(TavilyUnavailable):
            await provider.search("q")

    assert brk.state is State.OPEN


async def test_an_open_breaker_short_circuits_with_the_configured_message(fake_tavily):
    """AC-3: the operator is told plainly. §18.2 puts that string in config
    precisely so it is tunable without a deploy, so it must come from there
    and not be re-typed in the provider."""
    brk = breaker(failure_threshold=1)
    brk.record_failure()

    with pytest.raises(TavilyUnavailable) as caught:
        await provider_for(fake_tavily, brk).search("q")

    assert caught.value.degraded_mode == "SKIP_RESEARCH"
    assert caught.value.reason == (
        "Web research unavailable — questionnaire generated from what you provided."
    )


async def test_an_open_breaker_does_not_call_the_network(fake_tavily):
    """The whole point of the breaker.

    Counted at the server, not inferred: an earlier draft of this test
    asserted that an unrelated variable was unchanged, which would have passed
    just as happily if the request had been made.
    """
    brk = breaker(failure_threshold=1)
    brk.record_failure()
    provider = provider_for(fake_tavily, brk)

    before = fake_tavily["requests"]
    with pytest.raises(TavilyUnavailable):
        await provider.search("q")

    assert fake_tavily["requests"] == before, "the open breaker still called out"


async def test_a_closed_breaker_does_call_the_network(fake_tavily):
    """The control for the test above — otherwise a provider that never calls
    anything would pass it."""
    before = fake_tavily["requests"]

    await provider_for(fake_tavily).search("q")

    assert fake_tavily["requests"] == before + 1


async def test_it_recovers_when_the_dependency_does(fake_tavily):
    """The whole cycle against a real server: fail, open, wait, succeed, close."""
    import time

    fake_tavily["status"] = 500
    brk = breaker(failure_threshold=1, reset_timeout_seconds=1, success_threshold=1)
    provider = provider_for(fake_tavily, brk)

    with pytest.raises(TavilyUnavailable):
        await provider.search("q")
    assert brk.state is State.OPEN

    time.sleep(1.1)
    fake_tavily["status"] = 200
    fake_tavily["body"] = {
        "results": [{"title": "back", "url": "https://x.example", "content": "ok"}]
    }

    results = await provider.search("q")

    assert [r.url for r in results] == ["https://x.example"]
    assert brk.state is State.CLOSED


# ── An unconfigured key degrades, it does not crash ──────────────────


@pytest.mark.unit
async def test_no_api_key_degrades_with_a_distinct_reason():
    """CI and local development run without a Tavily key. The right behaviour
    is AC-3's degraded brief, and an operator should be able to tell a missing
    key from an outage."""
    provider = TavilyProvider("", breaker=breaker())

    assert provider.configured is False
    with pytest.raises(TavilyUnavailable, match="no Tavily API key"):
        await provider.search("q")


@pytest.mark.unit
async def test_a_missing_key_does_not_consume_the_breaker():
    """Otherwise a keyless environment would open the breaker on startup and
    report an outage that is really a configuration gap."""
    brk = breaker(failure_threshold=1)
    provider = TavilyProvider("", breaker=brk)

    with pytest.raises(TavilyUnavailable):
        await provider.search("q")

    assert brk.state is State.CLOSED
