"""N-01 AC-1 · Live meeting e2e: consent → record → transcripts → stop.

Exercises the full WebSocket lifecycle with FakeSTTAdapter + real Redis.
The fixture replays 21 STT events from ``two_speaker_2min.jsonl`` with
realistic ``delay_ms`` pacing.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from app.cache.redis_manager import TenantKeys

pytestmark = pytest.mark.e2e


def _collect_frames(ws, *, timeout: float = 15.0) -> list[dict]:
    """Read frames until the socket closes or timeout fires.

    Runs in a daemon thread so ``receive_text`` does not block the test
    forever if the server hangs.
    """
    frames: list[dict] = []
    done = threading.Event()

    def _reader():
        try:
            while True:
                raw = ws.receive_text()
                try:
                    frames.append(json.loads(raw))
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass
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

    done.wait(timeout=timeout)
    return frames


class TestLiveMeeting:
    def test_consent_to_transcript(self, e2e_client, live_company):
        """Open WS, start recording, receive transcript frames, stop."""
        tenant = f"live-{live_company}"
        session_id = f"sess-{live_company}-live"

        with e2e_client.websocket_connect(
            f"/v1/live/{session_id}?tenant_id={tenant}&ticket=tkt-1"
        ) as ws:
            frames = _collect_frames(ws)

        partials = [f for f in frames if f.get("type") == "transcript.partial"]
        finals = [f for f in frames if f.get("type") == "transcript.final"]

        assert len(partials) > 0, "expected at least one partial transcript"
        assert len(finals) > 0, "expected at least one final transcript"
        assert finals[0].get("t_start") is not None

    def test_transcript_stored_in_redis(
        self, e2e_client, live_company, app_with_live_redis
    ):
        """After a live session, transcript segments are stored in Redis."""
        import redis as sync_redis

        from tests.conftest import REDIS_URL

        tenant = f"live-redis-{live_company}"
        session_id = f"sess-{live_company}-redis"

        with e2e_client.websocket_connect(
            f"/v1/live/{session_id}?tenant_id={tenant}&ticket=tkt-1"
        ) as ws:
            _collect_frames(ws)

        r = sync_redis.Redis.from_url(REDIS_URL)
        keys = TenantKeys(tenant)
        frames_key = keys.live_frames(session_id)
        stored = r.llen(frames_key)
        r.close()

        assert stored > 0, "expected transcript frames buffered in Redis"
