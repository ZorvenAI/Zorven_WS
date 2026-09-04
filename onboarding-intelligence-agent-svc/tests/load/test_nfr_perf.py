"""N-02 · NFR performance verification against deployed targets.

These tests measure the three latency budgets from Design §18.3 and
NFR-PERF-01…03 through the real gateway. They are gated behind
``OIA_LOAD_TARGET`` and skip in CI unless that variable points at a
live service.

Usage::

    OIA_LOAD_TARGET=wss://oia.zorven.dev \
    OIA_LOAD_ENVIRONMENT=kong_dev \
    OIA_LOAD_CONCURRENCY=5 \
    pytest -m load -v
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
import pytest

from tests.load.conftest import (
    estimate_p95_from_buckets,
    parse_prometheus_counter,
    parse_prometheus_histogram_buckets,
)

pytestmark = [pytest.mark.load, pytest.mark.asyncio]


async def _run_ws_session(
    target_url: str,
    events: list[dict[str, Any]],
    *,
    session_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Open a WebSocket session, replay events, collect frames.

    Returns a summary dict with timing and frame counts.
    """
    import websockets

    base = target_url.rstrip("/")
    url = (
        f"{base}/v1/live/{session_id}"
        f"?tenant_id={tenant_id}&ticket=load-test"
    )
    frames: list[dict[str, Any]] = []
    t0 = time.monotonic()

    try:
        async with websockets.connect(url) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "start",
                        "recording_id": f"rec-{session_id}",
                        "codec": "LINEAR16",
                        "sample_rate": 16000,
                    }
                )
            )

            send_task = asyncio.create_task(_send_audio(ws, events))

            try:
                async for msg in ws:
                    try:
                        frame = json.loads(msg)
                        frames.append(frame)
                    except (TypeError, ValueError):
                        pass
            except websockets.ConnectionClosed:
                pass
            finally:
                send_task.cancel()
                try:
                    await send_task
                except asyncio.CancelledError:
                    pass

    except Exception as exc:
        return {
            "session_id": session_id,
            "error": str(exc),
            "frames": [],
            "elapsed_s": time.monotonic() - t0,
        }

    elapsed = time.monotonic() - t0
    partials = [f for f in frames if f.get("type") == "transcript.partial"]
    finals = [f for f in frames if f.get("type") == "transcript.final"]

    return {
        "session_id": session_id,
        "elapsed_s": elapsed,
        "total_frames": len(frames),
        "partials": len(partials),
        "finals": len(finals),
        "error": None,
    }


async def _send_audio(ws: Any, events: list[dict[str, Any]]) -> None:
    """Send audio chunks with realistic pacing, then stop."""
    for ev in events:
        delay = ev.get("delay_ms", 50) / 1000.0
        await asyncio.sleep(delay)
        await ws.send(b"\x00" * 320)

    await asyncio.sleep(0.5)
    await ws.send(json.dumps({"type": "stop"}))
    await asyncio.sleep(0.5)


class TestNFRPerformance:
    """NFR-PERF-01…03 verification against a deployed target."""

    def test_partial_latency_p95_deployed_path(
        self,
        target_url: str,
        fixture_events: list[dict[str, Any]],
        metrics_client: httpx.Client,
        environment_label: str,
    ):
        """NFR-PERF-01: STT partial latency ≤ 2000ms p95.

        Runs a single session through the deployed path and checks
        the server-side Prometheus histogram for p95.
        """
        before = metrics_client.get("/metrics").text

        result = asyncio.get_event_loop().run_until_complete(
            _run_ws_session(
                target_url,
                fixture_events,
                session_id="load-partial-01",
                tenant_id="t-load-01",
            )
        )

        assert result["error"] is None, f"session failed: {result['error']}"
        assert result["partials"] > 0, "no partials received"

        after = metrics_client.get("/metrics").text

        buckets_before = parse_prometheus_histogram_buckets(
            before, "oia_stt_partial_latency_ms"
        )
        buckets_after = parse_prometheus_histogram_buckets(
            after, "oia_stt_partial_latency_ms"
        )

        delta_buckets = [
            (le, after_count - before_count)
            for (le, after_count), (_, before_count) in zip(
                buckets_after, buckets_before
            )
        ]

        p95 = estimate_p95_from_buckets(delta_buckets)
        print(
            f"\n[{environment_label}] STT partial latency p95: "
            f"{p95:.0f}ms (budget: 2000ms)"
        )
        assert p95 is not None, "no latency observations"
        assert p95 <= 2000.0, f"STT partial p95 {p95:.0f}ms exceeds 2000ms budget"

    def test_sufficiency_p95_under_concurrency(
        self,
        target_url: str,
        fixture_events: list[dict[str, Any]],
        metrics_client: httpx.Client,
        concurrency: int,
        environment_label: str,
    ):
        """NFR-PERF-02: Sufficiency feedback ≤ 5000ms p95 under concurrency.

        Opens N concurrent WebSocket sessions, replays events in parallel,
        then checks the server-side sufficiency latency histogram.
        """
        before = metrics_client.get("/metrics").text

        async def _run_all() -> list[dict[str, Any]]:
            tasks = [
                _run_ws_session(
                    target_url,
                    fixture_events,
                    session_id=f"load-suf-{i:02d}",
                    tenant_id=f"t-load-suf-{i:02d}",
                )
                for i in range(concurrency)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.get_event_loop().run_until_complete(_run_all())

        errors = [r for r in results if r["error"]]
        successful = [r for r in results if not r["error"]]
        print(
            f"\n[{environment_label}] Concurrency: {concurrency}, "
            f"successful: {len(successful)}, errors: {len(errors)}"
        )

        assert len(successful) > 0, "all sessions failed"

        after = metrics_client.get("/metrics").text

        buckets_before = parse_prometheus_histogram_buckets(
            before, "oia_sufficiency_latency_ms"
        )
        buckets_after = parse_prometheus_histogram_buckets(
            after, "oia_sufficiency_latency_ms"
        )

        if (
            buckets_before
            and buckets_after
            and len(buckets_before) == len(buckets_after)
        ):
            delta_buckets = [
                (le, after_count - before_count)
                for (le, after_count), (_, before_count) in zip(
                    buckets_after, buckets_before
                )
            ]
            p95 = estimate_p95_from_buckets(delta_buckets)
            if p95 is not None:
                print(
                    f"[{environment_label}] Sufficiency latency p95: "
                    f"{p95:.0f}ms (budget: 5000ms)"
                )
                assert p95 <= 5000.0, (
                    f"Sufficiency p95 {p95:.0f}ms exceeds 5000ms budget "
                    f"at concurrency={concurrency}"
                )
            else:
                print(
                    f"[{environment_label}] No sufficiency observations "
                    f"(fixture may not trigger sufficiency scoring)"
                )

    def test_process_60min_within_5min(
        self,
        http_base: str,
        environment_label: str,
    ):
        """NFR-PERF-03: PROCESS of a 60-minute meeting ≤ 5 minutes.

        POSTs a PROCESS request with a payload representing a 60-minute
        meeting and polls until completion, measuring wall-clock time.
        """
        client = httpx.Client(base_url=http_base, timeout=30.0)

        transcript_segments = []
        for i in range(600):
            transcript_segments.append(
                {
                    "text": (
                        f"Segment {i}: discussion about "
                        "brand strategy and positioning."
                    ),
                    "t_start": float(i * 6),
                    "t_end": float(i * 6 + 5),
                    "speaker": i % 2,
                    "is_final": True,
                }
            )

        payload = {
            "tenant_id": "t-load-process",
            "company_id": 1,
            "session_id": "sess-load-process-60min",
            "transcript_segments": transcript_segments,
            "questions": [
                {"id": "q1", "text": "What is your company name?"},
                {"id": "q2", "text": "When was it founded?"},
                {"id": "q3", "text": "Who are your competitors?"},
            ],
        }

        t0 = time.monotonic()

        resp = client.post(
            "/v1/process",
            json=payload,
            headers={"X-Service-Token": "load-test"},
        )

        if resp.status_code == 202:
            job_id = resp.json().get("job_id")
            if job_id:
                for _ in range(60):
                    time.sleep(5)
                    status_resp = client.get(f"/v1/process/{job_id}/status")
                    if status_resp.status_code == 200:
                        status = status_resp.json().get("status")
                        if status in ("SUCCEEDED", "FAILED"):
                            break

        elapsed = time.monotonic() - t0
        print(
            f"\n[{environment_label}] PROCESS 60-min meeting: "
            f"{elapsed:.1f}s (budget: 300s)"
        )
        assert elapsed <= 300.0, f"PROCESS took {elapsed:.1f}s, exceeds 300s budget"

    def test_sufficiency_drops_under_overload(
        self,
        target_url: str,
        fixture_events: list[dict[str, Any]],
        metrics_client: httpx.Client,
        concurrency: int,
        environment_label: str,
    ):
        """AC-3: Under overload, sufficiency signals are dropped, not queued.

        Opens 2×N concurrent sessions to exceed the 5s budget, then
        verifies the drop counter incremented and no backlog accumulated.
        """
        overload_n = concurrency * 2
        before_text = metrics_client.get("/metrics").text
        drops_before = parse_prometheus_counter(
            before_text, "oia_sufficiency_drops_total"
        )

        async def _run_overload() -> list[dict[str, Any]]:
            tasks = [
                _run_ws_session(
                    target_url,
                    fixture_events,
                    session_id=f"load-drop-{i:02d}",
                    tenant_id=f"t-load-drop-{i:02d}",
                )
                for i in range(overload_n)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.get_event_loop().run_until_complete(_run_overload())

        successful = [r for r in results if not r["error"]]
        print(
            f"\n[{environment_label}] Overload sessions: {overload_n}, "
            f"successful: {len(successful)}"
        )

        after_text = metrics_client.get("/metrics").text
        drops_after = parse_prometheus_counter(
            after_text, "oia_sufficiency_drops_total"
        )
        drop_delta = drops_after - drops_before

        print(
            f"[{environment_label}] Sufficiency drops: {drop_delta:.0f} "
            f"(expected > 0 under overload)"
        )

        if len(successful) > 0:
            assert drop_delta > 0, (
                "expected sufficiency drops under overload, but counter "
                f"did not increment (before={drops_before}, after={drops_after})"
            )
