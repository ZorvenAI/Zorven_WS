"""Phase B · backend write outbox.

Tests cover: enqueue/drain lifecycle, overflow bounding, startup scan,
breaker recovery trigger, corrupt entry handling, and the backend client
integration (writes are buffered when the breaker opens, replayed on
recovery).

Integration tests run against real Redis.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.cache.outbox import OutboxWriter, register_outbox_drain
from app.cache.redis_manager import TTL_OUTBOX
from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker, State
from app.services.backend_client import BackendClient

TENANT = "t-outbox-1"
TENANT_2 = "t-outbox-2"


def breaker(**overrides) -> CircuitBreaker:
    base = dict(
        name="backend",
        failure_threshold=2,
        window_seconds=30,
        success_threshold=1,
        half_open_max_calls=1,
        reset_timeout_seconds=300,
        degraded_mode="REDIS_OUTBOX",
        user_message="Saving is delayed.",
    )
    base.update(overrides)
    return CircuitBreaker(BreakerConfig(**base))


@pytest.fixture
def django_stub():
    state = {"status": 200, "body": {"ok": True}, "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            state["requests"].append(
                {
                    "method": self.command,
                    "path": self.path,
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

        do_POST = _handle
        do_PATCH = _handle

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


async def _cleanup_outbox(redis_mgr, *tenants):
    for tid in tenants:
        key = redis_mgr.keys_for(tid).backend_outbox()
        await redis_mgr.client.delete(key)


# ── OutboxWriter: enqueue and drain ──────────────────────────────────


@pytest.mark.integration
async def test_enqueue_adds_entry_to_redis(live_redis):
    outbox = OutboxWriter(live_redis)
    try:
        await outbox.enqueue(
            method="POST",
            path="/api/v1/test/",
            payload={"key": "value"},
            tenant_id=TENANT,
        )
        key = live_redis.keys_for(TENANT).backend_outbox()
        length = await live_redis.client.llen(key)
        assert length == 1

        raw = await live_redis.client.lindex(key, 0)
        entry = json.loads(raw)
        assert entry["method"] == "POST"
        assert entry["path"] == "/api/v1/test/"
        assert entry["payload"] == {"key": "value"}
        assert entry["tenant_id"] == TENANT
        assert "enqueued_at" in entry
    finally:
        await _cleanup_outbox(live_redis, TENANT)


@pytest.mark.integration
async def test_drain_replays_entries_fifo(live_redis):
    outbox = OutboxWriter(live_redis)
    replayed = []

    async def replay_fn(entry):
        replayed.append(entry)
        return True

    try:
        await outbox.enqueue(
            method="POST", path="/first/", payload={}, tenant_id=TENANT
        )
        await outbox.enqueue(
            method="PATCH", path="/second/", payload={}, tenant_id=TENANT
        )

        count = await outbox.drain_all(replay_fn)

        assert count == 2
        assert replayed[0]["path"] == "/first/"
        assert replayed[1]["path"] == "/second/"

        key = live_redis.keys_for(TENANT).backend_outbox()
        assert await live_redis.client.llen(key) == 0
    finally:
        await _cleanup_outbox(live_redis, TENANT)


@pytest.mark.integration
async def test_drain_stops_on_replay_failure(live_redis):
    outbox = OutboxWriter(live_redis)
    call_count = 0

    async def replay_fn(entry):
        nonlocal call_count
        call_count += 1
        return call_count == 1

    try:
        await outbox.enqueue(method="POST", path="/a/", payload={}, tenant_id=TENANT)
        await outbox.enqueue(method="POST", path="/b/", payload={}, tenant_id=TENANT)
        await outbox.enqueue(method="POST", path="/c/", payload={}, tenant_id=TENANT)

        count = await outbox.drain_all(replay_fn)

        assert count == 1
        key = live_redis.keys_for(TENANT).backend_outbox()
        remaining = await live_redis.client.llen(key)
        assert remaining == 2

        raw = await live_redis.client.lindex(key, 0)
        entry = json.loads(raw)
        assert entry["path"] == "/b/"
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── Overflow bounding ────────────────────────────────────────────────


@pytest.mark.integration
async def test_overflow_drops_oldest(live_redis):
    outbox = OutboxWriter(live_redis, max_entries=3)

    try:
        for i in range(5):
            await outbox.enqueue(
                method="POST", path=f"/item-{i}/", payload={}, tenant_id=TENANT
            )

        key = live_redis.keys_for(TENANT).backend_outbox()
        length = await live_redis.client.llen(key)
        assert length == 3

        first = json.loads(await live_redis.client.lindex(key, 0))
        assert first["path"] == "/item-2/"

        last = json.loads(await live_redis.client.lindex(key, 2))
        assert last["path"] == "/item-4/"
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── Overflow callback ────────────────────────────────────────────────


@pytest.mark.integration
async def test_overflow_fires_callback(live_redis):
    overflow_calls = []

    async def on_overflow(tenant_id, dropped):
        overflow_calls.append((tenant_id, dropped))

    outbox = OutboxWriter(live_redis, max_entries=2, on_overflow=on_overflow)

    try:
        for i in range(4):
            await outbox.enqueue(
                method="POST", path=f"/item-{i}/", payload={}, tenant_id=TENANT
            )

        assert len(overflow_calls) == 2
        assert overflow_calls[0] == (TENANT, 1)
        assert overflow_calls[1] == (TENANT, 1)
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── Multi-tenant drain ──────────────────────────────────────────────


@pytest.mark.integration
async def test_drain_covers_multiple_tenants(live_redis):
    outbox = OutboxWriter(live_redis)
    replayed = []

    async def replay_fn(entry):
        replayed.append(entry["tenant_id"])
        return True

    try:
        await outbox.enqueue(method="POST", path="/a/", payload={}, tenant_id=TENANT)
        await outbox.enqueue(method="POST", path="/b/", payload={}, tenant_id=TENANT_2)

        count = await outbox.drain_all(replay_fn)

        assert count == 2
        assert set(replayed) == {TENANT, TENANT_2}
    finally:
        await _cleanup_outbox(live_redis, TENANT, TENANT_2)


# ── Cross-tenant drain continues ───────────────────────────────────


@pytest.mark.integration
async def test_drain_continues_to_next_tenant_on_failure(live_redis):
    """A replay failure for one tenant must not block other tenants."""
    outbox = OutboxWriter(live_redis)
    FAIL_TENANT = "t-outbox-fail"
    OK_TENANT = "t-outbox-ok"

    async def replay_fn(entry):
        return entry["tenant_id"] != FAIL_TENANT

    try:
        await outbox.enqueue(
            method="POST", path="/a/", payload={}, tenant_id=FAIL_TENANT
        )
        await outbox.enqueue(method="POST", path="/b/", payload={}, tenant_id=OK_TENANT)

        count = await outbox.drain_all(replay_fn)

        assert count >= 1
        ok_key = live_redis.keys_for(OK_TENANT).backend_outbox()
        assert await live_redis.client.llen(ok_key) == 0

        fail_key = live_redis.keys_for(FAIL_TENANT).backend_outbox()
        assert await live_redis.client.llen(fail_key) == 1
    finally:
        await _cleanup_outbox(live_redis, FAIL_TENANT, OK_TENANT)


# ── TTL is set ───────────────────────────────────────────────────────


@pytest.mark.integration
async def test_outbox_key_has_ttl(live_redis):
    outbox = OutboxWriter(live_redis)

    try:
        await outbox.enqueue(method="POST", path="/x/", payload={}, tenant_id=TENANT)

        key = live_redis.keys_for(TENANT).backend_outbox()
        ttl = await live_redis.client.ttl(key)
        assert 0 < ttl <= TTL_OUTBOX
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── Corrupt entry handling ───────────────────────────────────────────


@pytest.mark.integration
async def test_corrupt_entry_is_skipped(live_redis):
    outbox = OutboxWriter(live_redis)
    replayed = []

    async def replay_fn(entry):
        replayed.append(entry)
        return True

    try:
        key = live_redis.keys_for(TENANT).backend_outbox()
        await live_redis.client.rpush(key, "not-valid-json")
        await outbox.enqueue(method="POST", path="/good/", payload={}, tenant_id=TENANT)

        count = await outbox.drain_all(replay_fn)

        assert count == 1
        assert replayed[0]["path"] == "/good/"
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── Pending count ────────────────────────────────────────────────────


@pytest.mark.integration
async def test_pending_count(live_redis):
    outbox = OutboxWriter(live_redis)

    try:
        await outbox.enqueue(method="POST", path="/a/", payload={}, tenant_id=TENANT)
        await outbox.enqueue(method="POST", path="/b/", payload={}, tenant_id=TENANT_2)

        total = await outbox.pending_count()
        assert total == 2
    finally:
        await _cleanup_outbox(live_redis, TENANT, TENANT_2)


# ── Concurrent drain guard ──────────────────────────────────────────


@pytest.mark.integration
async def test_concurrent_drain_is_rejected(live_redis):
    outbox = OutboxWriter(live_redis)
    outbox._draining = True

    count = await outbox.drain_all(lambda e: True)
    assert count == 0

    outbox._draining = False


# ── BackendClient + Outbox integration ──────────────────────────────


@pytest.mark.integration
async def test_open_breaker_enqueues_post(live_redis, django_stub):
    outbox = OutboxWriter(live_redis)
    brk = breaker(failure_threshold=1)
    brk.record_failure()
    assert brk.state is State.OPEN

    client = BackendClient(django_stub["url"], "tok", breaker=brk, outbox=outbox)

    try:
        result = await client.store_research_brief(
            tenant_id=TENANT,
            company_name="TestCo",
            brief={"facts": [], "degraded": False, "company_name": "TestCo"},
        )

        assert result is False
        assert django_stub["requests"] == []

        key = live_redis.keys_for(TENANT).backend_outbox()
        length = await live_redis.client.llen(key)
        assert length == 1

        entry = json.loads(await live_redis.client.lindex(key, 0))
        assert entry["method"] == "POST"
        assert "upsert" in entry["path"]
        assert entry["tenant_id"] == TENANT
    finally:
        await _cleanup_outbox(live_redis, TENANT)


@pytest.mark.integration
async def test_open_breaker_enqueues_patch(live_redis, django_stub):
    outbox = OutboxWriter(live_redis)
    brk = breaker(failure_threshold=1)
    brk.record_failure()

    client = BackendClient(django_stub["url"], "tok", breaker=brk, outbox=outbox)

    try:
        result = await client.update_asset_ocr(
            tenant_id=TENANT,
            asset_id=42,
            ocr_text="hello",
            ocr_confidence=0.95,
            sensitivity_class="PUBLIC",
            rag_excluded=False,
        )

        assert result is False
        key = live_redis.keys_for(TENANT).backend_outbox()
        length = await live_redis.client.llen(key)
        assert length == 1

        entry = json.loads(await live_redis.client.lindex(key, 0))
        assert entry["method"] == "PATCH"
        assert "42/ocr/" in entry["path"]
    finally:
        await _cleanup_outbox(live_redis, TENANT)


@pytest.mark.integration
async def test_replay_entry_succeeds(live_redis, django_stub):
    brk = breaker()
    client = BackendClient(django_stub["url"], "tok", breaker=brk)

    ok = await client.replay_entry(
        {
            "method": "POST",
            "path": "/api/v1/test/",
            "payload": {"x": 1},
            "tenant_id": TENANT,
            "timeout": 5.0,
        }
    )

    assert ok is True
    assert len(django_stub["requests"]) == 1
    assert django_stub["requests"][0]["path"] == "/api/v1/test/"


@pytest.mark.integration
async def test_replay_entry_fails_on_server_error(live_redis, django_stub):
    django_stub["status"] = 500
    brk = breaker()
    client = BackendClient(django_stub["url"], "tok", breaker=brk)

    ok = await client.replay_entry(
        {
            "method": "POST",
            "path": "/api/v1/test/",
            "payload": {},
            "tenant_id": TENANT,
        }
    )

    assert ok is False


@pytest.mark.integration
async def test_replay_entry_treats_4xx_as_success(live_redis, django_stub):
    """A 4xx is non-retryable — the request was malformed, not the backend."""
    django_stub["status"] = 400
    brk = breaker()
    client = BackendClient(django_stub["url"], "tok", breaker=brk)

    ok = await client.replay_entry(
        {
            "method": "POST",
            "path": "/api/v1/test/",
            "payload": {},
            "tenant_id": TENANT,
        }
    )

    assert ok is True


@pytest.mark.integration
async def test_replay_entry_returns_false_when_breaker_open(live_redis, django_stub):
    brk = breaker(failure_threshold=1)
    brk.record_failure()
    client = BackendClient(django_stub["url"], "tok", breaker=brk)

    ok = await client.replay_entry(
        {"method": "POST", "path": "/x/", "payload": {}, "tenant_id": TENANT}
    )

    assert ok is False
    assert django_stub["requests"] == []


# ── End-to-end: enqueue → recover → drain ────────────────────────────


@pytest.mark.integration
async def test_full_outbox_lifecycle(live_redis, django_stub):
    """Open breaker → writes buffered → breaker closes → drain replays."""
    outbox = OutboxWriter(live_redis)
    brk = breaker(failure_threshold=1)
    client = BackendClient(django_stub["url"], "tok", breaker=brk, outbox=outbox)

    try:
        brk.record_failure()
        assert brk.state is State.OPEN

        await client.store_research_brief(
            tenant_id=TENANT,
            company_name="A",
            brief={"facts": [], "degraded": False, "company_name": "A"},
        )
        await client.update_asset_ocr(
            tenant_id=TENANT,
            asset_id=1,
            ocr_text="t",
            ocr_confidence=0.9,
            sensitivity_class="PUBLIC",
            rag_excluded=False,
        )

        assert django_stub["requests"] == []
        key = live_redis.keys_for(TENANT).backend_outbox()
        assert await live_redis.client.llen(key) == 2

        brk.reset()
        assert brk.state is State.CLOSED

        count = await outbox.drain_all(client.replay_entry)

        assert count == 2
        assert len(django_stub["requests"]) == 2
        assert django_stub["requests"][0]["method"] == "POST"
        assert django_stub["requests"][1]["method"] == "PATCH"
        assert await live_redis.client.llen(key) == 0
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── Breaker callback wiring ─────────────────────────────────────────


@pytest.mark.integration
async def test_register_outbox_drain_fires_on_close(live_redis, django_stub):
    """The drain callback fires when the breaker transitions to CLOSED."""
    import asyncio

    outbox = OutboxWriter(live_redis)
    brk = breaker(failure_threshold=1)
    client = BackendClient(django_stub["url"], "tok", breaker=brk, outbox=outbox)

    register_outbox_drain(brk, outbox, client.replay_entry)

    try:
        brk.record_failure()
        key = live_redis.keys_for(TENANT).backend_outbox()
        await live_redis.client.rpush(
            key,
            json.dumps(
                {
                    "method": "POST",
                    "path": "/api/v1/test/",
                    "payload": {"x": 1},
                    "tenant_id": TENANT,
                    "timeout": 5.0,
                }
            ),
        )
        await live_redis.client.expire(key, TTL_OUTBOX)

        brk.reset()

        await asyncio.sleep(0.3)

        assert len(django_stub["requests"]) == 1
        assert await live_redis.client.llen(key) == 0
    finally:
        await _cleanup_outbox(live_redis, TENANT)


# ── No outbox → old behavior preserved ──────────────────────────────


@pytest.mark.unit
async def test_no_outbox_still_returns_none():
    """Without an outbox, the original drop-on-open behavior is preserved."""
    brk = breaker(failure_threshold=1)
    brk.record_failure()
    client = BackendClient("http://127.0.0.1:1", "tok", breaker=brk)

    result = await client.store_research_brief(
        tenant_id="t-1",
        company_name="K",
        brief={"facts": [], "degraded": False, "company_name": "K"},
    )
    assert result is False


@pytest.mark.unit
async def test_replay_entry_returns_false_when_not_configured():
    client = BackendClient("", "tok", breaker=breaker())
    ok = await client.replay_entry(
        {"method": "POST", "path": "/x/", "payload": {}, "tenant_id": "t-1"}
    )
    assert ok is False
