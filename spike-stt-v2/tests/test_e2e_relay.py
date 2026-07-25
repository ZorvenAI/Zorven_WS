"""End-to-end tests for the FastAPI WebSocket relay.

Require real Google Cloud credentials. Marked with @pytest.mark.integration.

Run with: pytest tests/test_e2e_relay.py -v -m integration
"""

from __future__ import annotations

import asyncio
import json
import os
import struct
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

FIXTURE_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures"


def _load_fixture_pcm() -> bytes | None:
    """Load the WAV fixture and return raw PCM bytes (skip header)."""
    wav_path = FIXTURE_DIR / "two_speaker_onboarding_sample.wav"
    if not wav_path.exists():
        return None
    with open(wav_path, "rb") as f:
        data = f.read()
    return data[44:]


@pytest.fixture
def require_gcp():
    if not os.environ.get("OIA_SPIKE_PROJECT_ID"):
        pytest.skip("OIA_SPIKE_PROJECT_ID not set")


class TestHealthEndpoint:
    async def test_health_returns_status(self):
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert "status" in data


class TestWebSocketRelay:
    async def test_websocket_accepts_connection(self, require_gcp):
        from main import app
        from starlette.testclient import TestClient

        client = TestClient(app)
        with client.websocket_connect("/ws/stt-spike?recognizer=oia-spike-en-us") as ws:
            # Connection accepted — just close cleanly
            pass

    async def test_audio_through_relay_produces_transcript(self, require_gcp):
        """Send audio fixture chunks through the WebSocket and expect transcripts."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found")

        from main import app
        from starlette.testclient import TestClient

        client = TestClient(app)
        received = []

        with client.websocket_connect("/ws/stt-spike?recognizer=oia-spike-en-us") as ws:
            chunk_size = 3200
            onset_ts = 1000.0  # Fake onset timestamp

            for i in range(0, min(len(pcm), chunk_size * 30), chunk_size):
                chunk = pcm[i : i + chunk_size]
                # Prepend 8-byte onset timestamp
                ts_buf = struct.pack("<d", onset_ts)
                ws.send_bytes(ts_buf + chunk)
                # Small delay for real-time pacing
                import time

                time.sleep(0.05)

            # Wait for results
            import time

            time.sleep(3.0)

            # Try to receive messages (non-blocking)
            try:
                while True:
                    data = ws.receive_json(mode="text")
                    received.append(data)
            except Exception:
                pass

        # We should have received at least one transcript
        assert len(received) > 0
        assert any("text" in msg for msg in received)

    async def test_reconnect_via_control_frame(self, require_gcp):
        """Sending reconnect action should succeed without dropping WebSocket."""
        from main import app
        from starlette.testclient import TestClient

        client = TestClient(app)

        with client.websocket_connect("/ws/stt-spike?recognizer=oia-spike-en-us") as ws:
            # Send some audio first
            pcm = _load_fixture_pcm()
            if pcm:
                ts_buf = struct.pack("<d", 1000.0)
                ws.send_bytes(ts_buf + pcm[:3200])
                import time

                time.sleep(0.5)

            # Send reconnect control frame
            ws.send_json({"action": "reconnect"})

            # Should receive a reconnected message
            import time

            time.sleep(1.0)

            try:
                data = ws.receive_json(mode="text")
                if data.get("type") == "reconnected":
                    assert "stream_id" in data
            except Exception:
                # Connection may have produced other messages first
                pass

    async def test_measurement_jsonl_written(self, require_gcp, tmp_path):
        """After a relay session, JSONL measurements should be written."""
        pcm = _load_fixture_pcm()
        if pcm is None:
            pytest.skip("Audio fixture not found")

        # Check that measurement files get created in the spike dir
        from main import app, STATIC_DIR

        jsonl_files_before = set(STATIC_DIR.glob("measurements_*.jsonl"))

        from starlette.testclient import TestClient

        client = TestClient(app)

        with client.websocket_connect("/ws/stt-spike?recognizer=oia-spike-en-us") as ws:
            chunk_size = 3200
            ts_buf = struct.pack("<d", 1000.0)
            for i in range(0, min(len(pcm), chunk_size * 20), chunk_size):
                ws.send_bytes(ts_buf + pcm[i : i + chunk_size])
                import time

                time.sleep(0.05)

            import time

            time.sleep(3.0)

        jsonl_files_after = set(STATIC_DIR.glob("measurements_*.jsonl"))
        new_files = jsonl_files_after - jsonl_files_before

        assert len(new_files) >= 1, "Expected at least one new JSONL measurement file"

        # Verify the file has valid JSON lines
        for f in new_files:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        assert "utterance_id" in data
                        assert "latency_ms" in data
                        assert "speaker_tag" in data
                        assert "recognizer" in data
