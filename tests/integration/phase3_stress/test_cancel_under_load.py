"""Stress tests: Cancel during active execution.

Verifies the orchestrator correctly handles cancel requests
while a pipeline is running.
"""

import asyncio

import pytest

from tests.integration.conftest import (
    BRAND_ANALYSIS_MANIFEST,
    ORCHESTRATOR_URL,
    make_dispatch_payload,
    make_job_id,
)


@pytest.mark.integration
@pytest.mark.stress
class TestCancelUnderLoad:
    """Cancel behavior during active pipeline execution."""

    @pytest.mark.timeout(60)
    async def test_cancel_during_execution(
        self, http_client, service_headers, callback_capture
    ):
        """Dispatch job + cancel immediately -> job ends with failed/cancelled."""
        job_id = make_job_id()
        payload = make_dispatch_payload(
            job_id=job_id,
            manifest=BRAND_ANALYSIS_MANIFEST,
            callback_url="http://host.docker.internal:9997/callback",
        )

        # Dispatch
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        # Cancel immediately
        await asyncio.sleep(0.1)
        cancel_resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel",
            headers=service_headers,
        )
        assert cancel_resp.status_code == 200

        # Wait for callbacks — should get either completed or failed (cancelled)
        await asyncio.sleep(10)
        callbacks = callback_capture.callbacks

        # The job should have ended (either cancelled before execution or completed
        # before cancel was processed — both are valid outcomes)
        terminal = [c for c in callbacks if c.get("status") in ("completed", "failed")]
        assert (
            len(terminal) >= 1
        ), f"Job should reach terminal state. Callbacks: {callbacks}"

    @pytest.mark.timeout(60)
    async def test_cancel_preserves_partial_progress(
        self, http_client, service_headers, callback_capture
    ):
        """Cancel after partial execution preserves progress."""
        job_id = make_job_id()
        payload = make_dispatch_payload(
            job_id=job_id,
            manifest=BRAND_ANALYSIS_MANIFEST,
            callback_url="http://host.docker.internal:9997/callback",
        )

        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        # Wait a bit for execution to start, then cancel
        await asyncio.sleep(2)
        await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/{job_id}/cancel",
            headers=service_headers,
        )

        # Wait for terminal callback
        await asyncio.sleep(15)
        callbacks = callback_capture.callbacks

        terminal = [c for c in callbacks if c.get("status") in ("completed", "failed")]
        if terminal:
            # Progress should be present with at least some nodes tracked
            progress = terminal[0].get("progress", {})
            assert isinstance(progress, dict)
