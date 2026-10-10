"""#662 · interruption markers survive the socket, against real Redis.

The unit tests exercise `compute_transcript_coverage` on marker dicts handed to
it directly. What they cannot show is the part the bug actually turned on: the
markers are written by a socket teardown and read, much later and usually from
another Cloud Run instance, by finalisation. Nothing in process carries them —
Redis does, or the transcript goes out unlabelled.

Real Redis, no mocks, per this service's testing rule.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.cache.redis_manager import RedisManager, TenantKeys
from app.core.config import Settings
from app.logic.live_session import LiveSessionManager
from app.skills.summarize_recording import compute_transcript_coverage

pytestmark = [pytest.mark.integration]


@pytest.fixture
async def manager(monkeypatch):
    from tests.conftest import REDIS_URL, redis_available

    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")

    monkeypatch.setenv("OIA_REDIS_URL", REDIS_URL)
    monkeypatch.setenv("OIA_BACKEND_BASE_URL", "http://backend:8001")
    monkeypatch.setenv("OIA_GCS_BUCKET", "zorven-raw-assets")
    mgr = RedisManager(Settings())  # type: ignore[call-arg]
    await mgr.connect()
    yield mgr
    await mgr.close()


@pytest.fixture
async def session(manager):
    tenant = f"tenant-{uuid.uuid4().hex[:8]}"
    session_id = f"s-{uuid.uuid4().hex[:8]}"
    mgr = LiveSessionManager(redis=manager, tenant_id=tenant, session_id=session_id)
    yield mgr
    await manager.client.delete(TenantKeys(tenant).live_markers(session_id))


async def test_a_marker_outlives_the_session_object(session, manager):
    """Written by one object, read by another — the cross-instance case."""
    await session.record_marker(
        "transcript.interrupted", at=120.0, reason="socket_closed"
    )

    # A fresh manager for the same session, as finalisation would construct.
    reader = LiveSessionManager(
        redis=manager,
        tenant_id=session.tenant_id,
        session_id=session.session_id,
    )
    markers = await reader.read_markers()

    assert markers == [
        {"type": "transcript.interrupted", "at": 120.0, "reason": "socket_closed"}
    ]


async def test_markers_drive_coverage_end_to_end(session):
    """A drop and a reconnect, through Redis and out as coverage."""
    await session.record_marker(
        "transcript.interrupted", at=100.0, reason="socket_closed"
    )
    await session.record_marker("transcript.resumed", at=160.0)

    coverage = compute_transcript_coverage(await session.read_markers(), 0.0, 300.0)

    assert coverage["complete"] is False
    assert coverage["missing_s"] == 60.0
    assert coverage["gaps"] == [{"from": 100.0, "to": 160.0, "reason": "socket_closed"}]


async def test_an_untouched_session_reads_as_complete(session):
    """No markers at all — the key never even exists. This has to come back
    complete rather than erroring on a missing key, because it is the shape of
    every meeting that went fine."""
    coverage = compute_transcript_coverage(await session.read_markers(), 0.0, 300.0)

    assert coverage["complete"] is True
    assert coverage["missing_s"] == 0.0


async def test_markers_carry_a_ttl(session, manager):
    """Untrimmed keys evict other services' data from the shared DB 2, so
    every key this service writes carries a TTL (A-03)."""
    await session.record_marker("transcript.interrupted", at=10.0)

    key = TenantKeys(session.tenant_id).live_markers(session.session_id)
    ttl = await manager.client.ttl(key)

    assert ttl > 0, "a marker key with no TTL is a leak on shared Redis"


async def test_markers_are_tenant_scoped(session, manager):
    """Another tenant's session with the same id must not see these."""
    await session.record_marker("transcript.interrupted", at=10.0)

    other = LiveSessionManager(
        redis=manager,
        tenant_id=f"tenant-{uuid.uuid4().hex[:8]}",
        session_id=session.session_id,
    )

    assert await other.read_markers() == []


async def test_a_corrupt_entry_does_not_break_the_read(session, manager):
    """One unparseable entry must not cost the rest of the record: the
    alternative is a legal transcript that silently loses its truncation
    marker because something else wrote junk."""
    key = TenantKeys(session.tenant_id).live_markers(session.session_id)
    await manager.client.rpush(key, "not json at all")
    await manager.client.rpush(key, json.dumps({"type": "noise"}))  # no `at`
    await session.record_marker("transcript.interrupted", at=42.0)

    markers = await session.read_markers()

    assert markers == [{"type": "transcript.interrupted", "at": 42.0}]
