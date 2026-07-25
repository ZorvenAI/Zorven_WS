"""FastAPI spike relay for A-01: STT v2 streaming latency measurement.

Serves a browser page that captures microphone audio via AudioWorklet,
streams it to Google Cloud STT v2, and measures end-to-end latency.

Usage:
    export OIA_SPIKE_PROJECT_ID=your-gcp-project-id
    uvicorn main:app --host 0.0.0.0 --port 8120
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from measurement import (
    Measurement,
    create_jsonl_path,
    write_measurement,
)
from stt_client import STTConfig, STTStreamingSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="STT v2 Spike — A-01")

STATIC_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------


def _get_config(recognizer_id: str = "oia-spike-en-us") -> STTConfig:
    project_id = os.environ.get("OIA_SPIKE_PROJECT_ID", "")
    if not project_id:
        raise ValueError(
            "OIA_SPIKE_PROJECT_ID environment variable must be set. "
            "This is your GCP project ID."
        )
    return STTConfig(
        project_id=project_id,
        location=os.environ.get("OIA_SPIKE_LOCATION", "us-central1"),
        recognizer_id=recognizer_id,
        credentials_json=os.environ.get("OIA_SPIKE_CREDENTIALS_JSON", ""),
        credentials_path=os.environ.get("OIA_SPIKE_CREDENTIALS_PATH", ""),
    )


# ---------------------------------------------------------------------------
# Static file routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the spike measurement page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/worklet.js")
async def serve_worklet():
    """Serve the AudioWorklet processor."""
    return FileResponse(
        STATIC_DIR / "worklet.js",
        media_type="application/javascript",
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    project_id = os.environ.get("OIA_SPIKE_PROJECT_ID", "")
    return {
        "status": "ok" if project_id else "unconfigured",
        "project_id": project_id[:8] + "..." if len(project_id) > 8 else project_id,
    }


# ---------------------------------------------------------------------------
# WebSocket relay
# ---------------------------------------------------------------------------


@app.websocket("/ws/stt-spike")
async def stt_relay(
    websocket: WebSocket,
    recognizer: str = Query(default="oia-spike-en-us"),
):
    """WebSocket endpoint that relays browser audio to STT v2.

    Binary frames from the browser:
        [8-byte float64 onset_ts_ms][PCM bytes]

    JSON frames to the browser:
        {type, text, is_final, speaker_tag, confidence, latency_ms, seq, ...}

    Control frames from the browser (JSON):
        {"action": "reconnect"} — force reconnect for label stability test
    """
    await websocket.accept()
    logger.info("WebSocket connected, recognizer=%s", recognizer)

    config = _get_config(recognizer_id=recognizer)
    session = STTStreamingSession(config)
    loop = asyncio.get_running_loop()

    jsonl_path = create_jsonl_path(output_dir=str(STATIC_DIR))
    logger.info("Measurements will be written to %s", jsonl_path)

    utterance_counter = 0
    current_onset_ts: float = 0.0
    seq = 0

    session.start(loop)

    async def consume_results():
        """Forward STT results back to the browser and log measurements."""
        nonlocal utterance_counter, current_onset_ts, seq

        async for result in session.results():
            now_ms = time.time() * 1000
            seq += 1

            # Compute latency if we have an onset timestamp
            latency_ms = 0.0
            if current_onset_ts > 0:
                latency_ms = now_ms - current_onset_ts

            frame = {
                "type": "transcript.final" if result.is_final else "transcript.partial",
                "seq": seq,
                "text": result.text,
                "is_final": result.is_final,
                "speaker_tag": result.speaker_tag,
                "confidence": round(result.confidence, 3),
                "latency_ms": round(latency_ms, 1),
                "stream_id": session.stream_id,
            }

            try:
                await websocket.send_json(frame)
            except Exception:
                break

            # Log the first partial for each utterance
            if not result.is_final and latency_ms > 0:
                utterance_counter += 1
                m = Measurement(
                    utterance_id=utterance_counter,
                    onset_ts_ms=current_onset_ts,
                    first_partial_ts_ms=now_ms,
                    latency_ms=latency_ms,
                    text=result.text,
                    is_final=False,
                    speaker_tag=result.speaker_tag,
                    recognizer=recognizer,
                )
                write_measurement(jsonl_path, m)
                # Reset onset for next utterance
                current_onset_ts = 0.0

    result_task = asyncio.create_task(consume_results())

    try:
        while True:
            data = await websocket.receive()

            if "bytes" in data and data["bytes"]:
                raw = data["bytes"]
                if len(raw) > 8:
                    # Extract onset timestamp from first 8 bytes
                    onset_ts = struct.unpack("<d", raw[:8])[0]
                    pcm = raw[8:]

                    if onset_ts > 0 and current_onset_ts == 0:
                        current_onset_ts = onset_ts

                    session.feed_audio(pcm)

            elif "text" in data and data["text"]:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("action") == "reconnect":
                        logger.info("Reconnect requested by client")
                        session.reconnect()
                        await websocket.send_json({
                            "type": "reconnected",
                            "seq": seq + 1,
                            "stream_id": session.stream_id,
                        })
                        seq += 1
                except json.JSONDecodeError:
                    pass

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    finally:
        session.close()
        result_task.cancel()
        try:
            await result_task
        except asyncio.CancelledError:
            pass
        logger.info(
            "Session ended. %d utterances measured. Data: %s",
            utterance_counter,
            jsonl_path,
        )
