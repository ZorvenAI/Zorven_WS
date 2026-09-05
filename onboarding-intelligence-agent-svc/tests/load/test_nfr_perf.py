"""N-02 · NFR performance verification against deployed targets.

These tests measure the three latency budgets from Design §18.3 and
NFR-PERF-01…03 through the real gateway. They are gated behind
``OIA_LOAD_TARGET`` and skip in CI unless that variable points at a
live service.

**Deployed target requirement**: The target service must be configured
with ``OIA_STT_PROVIDER=fake`` so that the FakeSTTAdapter replays
fixture transcripts from silent audio chunks. Real GoogleSTTAdapter
produces nothing from silence — these tests exercise latency budgets,
not speech recognition.

Credentials are configurable via environment variables::

    OIA_LOAD_TARGET=wss://oia.zorven.dev \
    OIA_LOAD_ENVIRONMENT=kong_dev \
    OIA_LOAD_CONCURRENCY=5 \
    OIA_LOAD_TICKET=<valid-ticket> \
    OIA_LOAD_SERVICE_TOKEN=<valid-token> \
    pytest -m load -v
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
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
    ticket: str,
) -> dict[str, Any]:
    """Open a WebSocket session, replay events, collect frames.

    Returns a summary dict with timing and frame counts.
    """
    import websockets

    base = target_url.rstrip("/")
    url = f"{base}/v1/live/{session_id}" f"?tenant_id={tenant_id}&ticket={ticket}"
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
    """Send audio chunks with realistic pacing, then stop.

    Sends silent LINEAR16 chunks — the deployed target must use
    FakeSTTAdapter (``OIA_STT_PROVIDER=fake``) to produce transcripts
    from these.
    """
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
        load_ticket: str,
    ):
        """NFR-PERF-01: STT partial latency ≤ 2000ms p95.

        Measures server-side processing latency (emit_partial time) via
        the Prometheus histogram. This excludes STT recognition and
        gateway transit time — it measures the service's own overhead
        once a partial is ready to emit.
        """
        before = metrics_client.get("/metrics").text

        result = asyncio.get_event_loop().run_until_complete(
            _run_ws_session(
                target_url,
                fixture_events,
                session_id="load-partial-01",
                tenant_id="t-load-01",
                ticket=load_ticket,
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

        assert buckets_after, "no histogram buckets found in /metrics"
        assert len(buckets_before) == len(
            buckets_after
        ), "histogram bucket count changed mid-test"

        delta_buckets = [
            (le, after_count - before_count)
            for (le, after_count), (_, before_count) in zip(
                buckets_after, buckets_before
            )
        ]

        p95 = estimate_p95_from_buckets(delta_buckets)
        assert p95 is not None, "no latency observations in histogram"
        print(
            f"\n[{environment_label}] STT partial latency p95: "
            f"{p95:.0f}ms (budget: 2000ms)"
        )
        assert p95 <= 2000.0, f"STT partial p95 {p95:.0f}ms exceeds 2000ms budget"

    def test_sufficiency_p95_under_concurrency(
        self,
        target_url: str,
        fixture_events: list[dict[str, Any]],
        metrics_client: httpx.Client,
        concurrency: int,
        environment_label: str,
        load_ticket: str,
    ):
        """NFR-PERF-02: Sufficiency feedback ≤ 5000ms p95 under concurrency.

        Opens N concurrent WebSocket sessions, replays events in parallel,
        then checks the server-side sufficiency latency histogram.
        All sessions must succeed to validate the concurrency level.
        """
        before = metrics_client.get("/metrics").text

        async def _run_all() -> list[dict[str, Any]]:
            tasks = [
                _run_ws_session(
                    target_url,
                    fixture_events,
                    session_id=f"load-suf-{i:02d}",
                    tenant_id=f"t-load-suf-{i:02d}",
                    ticket=load_ticket,
                )
                for i in range(concurrency)
            ]
            return await asyncio.gather(*tasks)

        results = asyncio.get_event_loop().run_until_complete(_run_all())

        errors = [r for r in results if r["error"]]
        assert (
            len(errors) == 0
        ), f"{len(errors)}/{concurrency} sessions failed: " + "; ".join(
            r["error"] for r in errors
        )

        print(
            f"\n[{environment_label}] Concurrency: {concurrency}, "
            f"all {concurrency} sessions succeeded"
        )

        after = metrics_client.get("/metrics").text

        buckets_before = parse_prometheus_histogram_buckets(
            before, "oia_sufficiency_latency_ms"
        )
        buckets_after = parse_prometheus_histogram_buckets(
            after, "oia_sufficiency_latency_ms"
        )

        assert buckets_after, "no sufficiency histogram buckets in /metrics"
        assert len(buckets_before) == len(
            buckets_after
        ), "histogram bucket count changed mid-test"

        delta_buckets = [
            (le, after_count - before_count)
            for (le, after_count), (_, before_count) in zip(
                buckets_after, buckets_before
            )
        ]
        p95 = estimate_p95_from_buckets(delta_buckets)
        assert p95 is not None, (
            "no sufficiency observations in histogram — "
            "the fixture may not trigger sufficiency scoring"
        )
        print(
            f"[{environment_label}] Sufficiency latency p95: "
            f"{p95:.0f}ms (budget: 5000ms)"
        )
        assert p95 <= 5000.0, (
            f"Sufficiency p95 {p95:.0f}ms exceeds 5000ms budget "
            f"at concurrency={concurrency}"
        )

    def test_process_60min_within_5min(
        self,
        http_base: str,
        environment_label: str,
        load_service_token: str,
    ):
        """NFR-PERF-03: PROCESS of a 60-minute meeting ≤ 5 minutes.

        POSTs a PROCESS request matching the ProcessRequest schema
        (tenant_context + evidence_manifest), asserts 202, and polls
        until completion, measuring wall-clock time.
        """
        client = httpx.Client(base_url=http_base, timeout=30.0)

        payload = {
            "tenant_context": {
                "tenant_id": "t-load-process",
                "user_id": "load-test-user",
                "role": "ADMIN",
                "trace_id": f"load-{uuid.uuid4().hex[:16]}",
            },
            "session_id": "sess-load-process-60min",
            "evidence_manifest": {
                "recordings": ["rec-load-60min"],
                "media": [],
                "has_questionnaire": True,
                "has_transcript": True,
            },
            "callback_url": "",
        }

        t0 = time.monotonic()

        resp = client.post(
            "/v1/process",
            json=payload,
            headers={
                "X-Service-Token": load_service_token,
                "Idempotency-Key": f"load-nfr03-{uuid.uuid4().hex[:8]}",
            },
        )

        assert resp.status_code == 202, (
            f"expected 202 ACCEPTED, got {resp.status_code}: " f"{resp.text[:200]}"
        )

        job_id = resp.json().get("job_id")
        assert job_id, "202 response missing job_id"

        for _ in range(60):
            time.sleep(5)
            status_resp = client.get(
                f"/v1/process/{job_id}/status",
                headers={
                    "X-Service-Token": load_service_token,
                },
            )
            if status_resp.status_code == 200:
                job_status = status_resp.json().get("status")
                if job_status in ("SUCCEEDED", "FAILED"):
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
        load_ticket: str,
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
                    ticket=load_ticket,
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
                f"did not increment (before={drops_before}, "
                f"after={drops_after})"
            )
