"""Stress tests: Concurrent pipeline execution.

Verifies the system handles multiple simultaneous dispatches
without interference or failures.
"""

import asyncio

import pytest

from tests.integration.conftest import (
    BRAND_ANALYSIS_MANIFEST,
    COMPETITOR_AUDIT_MANIFEST,
    CONTENT_STRATEGY_MANIFEST,
    ORCHESTRATOR_URL,
    make_dispatch_payload,
    make_job_id,
)


@pytest.mark.integration
@pytest.mark.stress
class TestConcurrentPipelines:
    """Multiple simultaneous pipeline executions."""

    @pytest.mark.timeout(120)
    async def test_5_concurrent_dispatches(
        self, http_client, service_headers, callback_capture
    ):
        """5 simultaneous dispatches all return 202 and eventually complete."""
        tasks = []
        for i in range(5):
            payload = make_dispatch_payload(
                job_id=f"concurrent-{i}-{make_job_id()}",
                manifest=CONTENT_STRATEGY_MANIFEST,
                callback_url="http://host.docker.internal:9997/callback",
            )
            tasks.append(
                http_client.post(
                    f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
                    json=payload,
                    headers=service_headers,
                )
            )

        responses = await asyncio.gather(*tasks)
        for resp in responses:
            assert resp.status_code == 202

        # Wait for all 5 to complete
        completed = await callback_capture.wait_for_completed_count(5, timeout=60)
        assert len(completed) >= 5, (
            f"Only {len(completed)}/5 pipelines completed. "
            f"Total callbacks: {len(callback_capture.callbacks)}"
        )

    @pytest.mark.timeout(120)
    async def test_concurrent_different_manifests(
        self, http_client, service_headers, callback_capture
    ):
        """3 different manifests dispatched simultaneously all complete."""
        manifests = [
            BRAND_ANALYSIS_MANIFEST,
            COMPETITOR_AUDIT_MANIFEST,
            CONTENT_STRATEGY_MANIFEST,
        ]
        tasks = []
        for i, manifest in enumerate(manifests):
            payload = make_dispatch_payload(
                job_id=f"multi-manifest-{i}-{make_job_id()}",
                manifest=manifest,
                callback_url="http://host.docker.internal:9997/callback",
            )
            tasks.append(
                http_client.post(
                    f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
                    json=payload,
                    headers=service_headers,
                )
            )

        responses = await asyncio.gather(*tasks)
        for resp in responses:
            assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed_count(3, timeout=60)
        assert len(completed) >= 3

    @pytest.mark.timeout(120)
    async def test_concurrent_same_tenant(
        self, http_client, service_headers, callback_capture
    ):
        """Multiple jobs for the same tenant don't interfere."""
        tasks = []
        for i in range(3):
            payload = make_dispatch_payload(
                job_id=f"same-tenant-{i}-{make_job_id()}",
                manifest=CONTENT_STRATEGY_MANIFEST,
                callback_url="http://host.docker.internal:9997/callback",
            )
            # All share tenant_id "1"
            tasks.append(
                http_client.post(
                    f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
                    json=payload,
                    headers=service_headers,
                )
            )

        responses = await asyncio.gather(*tasks)
        for resp in responses:
            assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed_count(3, timeout=60)
        assert len(completed) >= 3

        # All should have result_data
        for cb in completed:
            assert "result_data" in cb
            assert "findings" in cb["result_data"]
