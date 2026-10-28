"""M-04 — stuck-session watchdog tests.

Tests run against real Redis. The watchdog scans for session keys with stale
heartbeats and calls the backend to finalize them.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock

import pytest

from app.logic.watchdog import _scan_and_close

pytestmark = [pytest.mark.integration]

TIMEOUT_S = 300


@pytest.fixture
async def redis_client(live_redis):
    """Raw Redis client from the live_redis manager fixture."""
    return live_redis.client


@pytest.fixture
def mock_backend():
    backend = AsyncMock()
    backend.finalize_stuck_session = AsyncMock(return_value={"status": "GATHERED"})
    return backend


@pytest.fixture
def mock_events():
    events = AsyncMock()
    events.emit = AsyncMock()
    return events


async def _write_session_with_heartbeat(
    redis_client, tenant_id: str, session_id: str, heartbeat: float
):
    key = f"oia:v1:{tenant_id}:session:{session_id}"
    await redis_client.hset(key, "mode", "LIVE")
    await redis_client.hset(key, "last_heartbeat", str(heartbeat))
    await redis_client.expire(key, 3600)
    return key


async def _write_session_without_heartbeat(
    redis_client, tenant_id: str, session_id: str
):
    key = f"oia:v1:{tenant_id}:session:{session_id}"
    await redis_client.hset(key, "mode", "PREP")
    await redis_client.expire(key, 3600)
    return key


async def test_stuck_session_watchdog_finalises(
    redis_client, mock_backend, mock_events
):
    """A session with a stale heartbeat is finalized and the heartbeat cleared."""
    stale_hb = time.time() - TIMEOUT_S - 60
    key = await _write_session_with_heartbeat(
        redis_client, "tenant-1", "sess-stuck", stale_hb
    )

    closed = await _scan_and_close(redis_client, mock_backend, mock_events, TIMEOUT_S)

    assert closed == 1
    mock_backend.finalize_stuck_session.assert_called_once_with(
        tenant_id="tenant-1", session_id="sess-stuck"
    )

    hb = await redis_client.hget(key, "last_heartbeat")
    assert hb is None

    await redis_client.delete(key)
    await redis_client.delete("oia:v1:tenant-1:watchdog:sess-stuck")


async def test_watchdog_ignores_fresh_sessions(redis_client, mock_backend, mock_events):
    """A session with a recent heartbeat is left alone."""
    fresh_hb = time.time() - 10
    key = await _write_session_with_heartbeat(
        redis_client, "tenant-2", "sess-fresh", fresh_hb
    )

    closed = await _scan_and_close(redis_client, mock_backend, mock_events, TIMEOUT_S)

    assert closed == 0
    mock_backend.finalize_stuck_session.assert_not_called()

    await redis_client.delete(key)


async def test_watchdog_ignores_sessions_without_heartbeat(
    redis_client, mock_backend, mock_events
):
    """PREP/PROCESS sessions have no heartbeat and should be skipped."""
    key = await _write_session_without_heartbeat(redis_client, "tenant-3", "sess-prep")

    closed = await _scan_and_close(redis_client, mock_backend, mock_events, TIMEOUT_S)

    assert closed == 0
    mock_backend.finalize_stuck_session.assert_not_called()

    await redis_client.delete(key)


async def test_watchdog_retains_heartbeat_on_finalize_failure(
    redis_client, mock_backend, mock_events
):
    """When Django returns None (failure), the heartbeat stays so next sweep retries."""
    mock_backend.finalize_stuck_session = AsyncMock(return_value=None)
    stale_hb = time.time() - TIMEOUT_S - 60
    key = await _write_session_with_heartbeat(
        redis_client, "tenant-5", "sess-fail", stale_hb
    )

    closed = await _scan_and_close(redis_client, mock_backend, mock_events, TIMEOUT_S)

    assert closed == 0
    hb = await redis_client.hget(key, "last_heartbeat")
    assert hb is not None

    await redis_client.delete(key)
    await redis_client.delete("oia:v1:tenant-5:watchdog:sess-fail")


async def test_watchdog_skips_summary_keys(redis_client, mock_backend, mock_events):
    """Summary keys should not be treated as sessions."""
    key = "oia:v1:tenant-4:session:sess-4:summary"
    await redis_client.set(key, "some-summary")
    await redis_client.expire(key, 3600)

    closed = await _scan_and_close(redis_client, mock_backend, mock_events, TIMEOUT_S)

    assert closed == 0

    await redis_client.delete(key)


async def test_a_wrong_type_key_does_not_end_the_sweep(
    redis_client, mock_backend, mock_events
):
    """§3.3: one key of the wrong type used to abort the whole pass.

    The assertion that matters is not "no exception" but that the stuck
    session **after** the bad key is still finalised. A guard that swallowed
    the error and stopped scanning would pass an exception-only test while
    leaving the defect exactly as it was: sessions later in scan order never
    examined, silently, on every sweep.

    `tests/e2e/test_gdpr_erasure.py` is how this arises in practice -- it
    seeds every key with `set(k, "test-data")`, including the session path
    where production writes a hash. DB 2 is shared with ten other services,
    so a foreign key at this path is not something this service controls.
    """
    tenant = "wrongtype-t1"
    bad_key = f"oia:v1:{tenant}:session:aaa-not-a-hash"
    await redis_client.set(bad_key, "test-data", ex=3600)

    stale = time.time() - (TIMEOUT_S + 60)
    good_key = await _write_session_with_heartbeat(
        redis_client, tenant, "zzz-stuck-after-the-bad-key", stale
    )
    claim = f"oia:v1:{tenant}:watchdog:zzz-stuck-after-the-bad-key"
    await redis_client.delete(claim)

    try:
        closed = await _scan_and_close(
            redis_client, mock_backend, mock_events, TIMEOUT_S
        )

        assert closed >= 1, (
            "the stuck session was not finalised, so the wrong-type key is "
            "still cutting the sweep short"
        )
        finalised = [
            c.kwargs.get("session_id")
            for c in mock_backend.finalize_stuck_session.await_args_list
        ]
        assert "zzz-stuck-after-the-bad-key" in finalised, finalised
    finally:
        await redis_client.delete(bad_key, good_key, claim)
