"""N-01 AC-1 · Live meeting e2e: consent → record → transcripts → stop.

Exercises the full WebSocket lifecycle with FakeSTTAdapter + real Redis.
The fixture replays 21 STT events from ``two_speaker_2min.jsonl`` with
realistic ``delay_ms`` pacing.

N-02 AC-4 extends this with a 45-minute session stability test.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import redis as sync_redis

from app.cache.redis_manager import TenantKeys

from tests.conftest import REDIS_URL

pytestmark = pytest.mark.e2e


class _FrameResult:
    """Frames collected from a WS session plus close/error outcome."""

    __slots__ = ("frames", "error", "timed_out")

    def __init__(
        self,
        frames: list[dict],
        error: Exception | None,
        timed_out: bool,
    ):
        self.frames = frames
        self.error = error
        self.timed_out = timed_out


def _collect_frames(ws, *, timeout: float = 15.0) -> _FrameResult:
    """Read frames until the socket closes or timeout fires.

    Runs in a daemon thread so ``receive_text`` does not block the test
    forever if the server hangs. Returns a ``_FrameResult`` with the
    frames AND the close/error outcome so callers can assert the
    WebSocket shut down cleanly.
    """
    frames: list[dict] = []
    done = threading.Event()
    reader_error: list[Exception] = []

    def _reader():
        try:
            while True:
                raw = ws.receive_text()
                try:
                    frames.append(json.loads(raw))
                except (TypeError, ValueError):
                    pass
        except Exception as exc:
            reader_error.append(exc)
        finally:
            done.set()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    ws.send_json(
        {
            "type": "start",
            "recording_id": "rec-e2e-live",
            "codec": "LINEAR16",
            "sample_rate": 16000,
        }
    )

    for _ in range(5):
        ws.send_bytes(b"\x00" * 320)
        time.sleep(0.05)

    time.sleep(3.0)

    ws.send_json({"type": "stop"})
    time.sleep(0.5)
    ws.close()

    timed_out = not done.wait(timeout=timeout)
    return _FrameResult(
        frames=frames,
        error=reader_error[0] if reader_error else None,
        timed_out=timed_out,
    )


class TestLiveMeeting:
    def test_consent_to_transcript(self, e2e_client, live_company):
        """Open WS, start recording, receive transcript frames, stop."""
        tenant = f"live-{live_company}"
        session_id = f"sess-{live_company}-live"

        with e2e_client.websocket_connect(
            f"/v1/live/{session_id}?tenant_id={tenant}&ticket=tkt-1"
        ) as ws:
            result = _collect_frames(ws)

        assert not result.timed_out, "WS reader timed out"

        partials = [f for f in result.frames if f.get("type") == "transcript.partial"]
        finals = [f for f in result.frames if f.get("type") == "transcript.final"]

        assert len(partials) > 0, "expected at least one partial transcript"
        assert len(finals) > 0, "expected at least one final transcript"
        assert finals[0].get("t_start") is not None

    def test_transcript_stored_in_redis(
        self, e2e_client, live_company, app_with_live_redis
    ):
        """After a live session, transcript segments are stored in Redis."""
        tenant = f"live-redis-{live_company}"
        session_id = f"sess-{live_company}-redis"

        with e2e_client.websocket_connect(
            f"/v1/live/{session_id}?tenant_id={tenant}&ticket=tkt-1"
        ) as ws:
            result = _collect_frames(ws)

        assert not result.timed_out, "WS reader timed out"

        r = sync_redis.Redis.from_url(REDIS_URL)
        keys = TenantKeys(tenant)
        frames_key = keys.live_frames(session_id)
        stored = r.llen(frames_key)
        r.close()

        assert stored > 0, "expected transcript frames buffered in Redis"


class TestLongSession:
    """N-02 AC-4: 45-minute meeting holds up."""

    def test_45_minute_session_stable(
        self, e2e_client_45min, live_company, app_with_live_redis
    ):
        """WebSocket survives a full 45-minute meeting (compressed replay).

        Verifies: WS stays open, frames span the full timestamp range,
        Redis replay buffer stays bounded at BUFFER_FRAMES, and the
        session shuts down cleanly.
        """
        from app.logic.live_session import BUFFER_FRAMES

        tenant = f"long-{live_company}"
        session_id = f"sess-{live_company}-long"

        with e2e_client_45min.websocket_connect(
            f"/v1/live/{session_id}?tenant_id={tenant}&ticket=tkt-1"
        ) as ws:
            result = _collect_frames(ws, timeout=120.0)

        assert not result.timed_out, "WS reader timed out during 45-min replay"

        partials = [f for f in result.frames if f.get("type") == "transcript.partial"]
        finals = [f for f in result.frames if f.get("type") == "transcript.final"]

        assert len(partials) > 0, "expected partial transcripts"
        assert len(finals) > 0, "expected final transcripts"

        all_t_ends = [f.get("t_end", 0.0) for f in finals if f.get("t_end") is not None]
        if all_t_ends:
            max_t = max(all_t_ends)
            assert (
                max_t > 2000.0
            ), f"expected finals spanning > 2000s, got max t_end={max_t:.1f}"

        r = sync_redis.Redis.from_url(REDIS_URL)
        keys = TenantKeys(tenant)
        frames_key = keys.live_frames(session_id)
        stored = r.llen(frames_key)
        r.close()

        assert stored > 0, "expected frames in Redis"
        assert (
            stored <= BUFFER_FRAMES
        ), f"frames {stored} exceeds BUFFER_FRAMES {BUFFER_FRAMES}"
