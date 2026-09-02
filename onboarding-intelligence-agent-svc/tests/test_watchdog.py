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


async def test_watchdog_skips_summary_keys(redis_client, mock_backend, mock_events):
    """Summary keys should not be treated as sessions."""
    key = "oia:v1:tenant-4:session:sess-4:summary"
    await redis_client.set(key, "some-summary")
    await redis_client.expire(key, 3600)

    closed = await _scan_and_close(redis_client, mock_backend, mock_events, TIMEOUT_S)

    assert closed == 0

    await redis_client.delete(key)
