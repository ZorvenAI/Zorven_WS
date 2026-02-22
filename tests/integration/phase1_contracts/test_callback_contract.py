"""Contract tests: Orchestrator -> Django callback payloads.

Dispatches jobs to the orchestrator with callback_url pointing to a local
aiohttp server, then validates the shape of each callback payload.
"""

import pytest

from tests.integration.conftest import (
    CONTENT_STRATEGY_MANIFEST,
    ALL_AVAILABLE_MANIFESTS,
    ORCHESTRATOR_URL,
    make_dispatch_payload,
)


@pytest.mark.integration
class TestCallbackContract:
    """Validate callback PATCH payloads sent by the orchestrator."""

    async def test_callback_running_schema(
        self, http_client, service_headers, callback_capture
    ):
        """First callback should be 'running' with initial progress."""
        payload = make_dispatch_payload(
            manifest=CONTENT_STRATEGY_MANIFEST,
            callback_url="http://host.docker.internal:9999/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        callbacks = await callback_capture.wait_for_callbacks(1, timeout=15)
        assert len(callbacks) >= 1

        running_cb = callbacks[0]
        assert running_cb.get("status") == "running"
        assert "progress" in running_cb
        assert isinstance(running_cb["progress"], dict)

    async def test_callback_completed_schema(
        self, http_client, service_headers, callback_capture
    ):
        """Final callback should be 'completed' with result_data and progress."""
        payload = make_dispatch_payload(
            manifest=CONTENT_STRATEGY_MANIFEST,
            callback_url="http://host.docker.internal:9999/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        # Content-strategy is all internal, should complete fast
        callbacks = await callback_capture.wait_for_callbacks(2, timeout=20)

        # Find the completed callback
        completed = [c for c in callbacks if c.get("status") == "completed"]
        assert len(completed) >= 1, f"No completed callback found in: {callbacks}"

        cb = completed[0]
        assert "result_data" in cb
        assert "progress" in cb
        assert isinstance(cb["result_data"], dict)
        assert "findings" in cb["result_data"]
        assert "recommendations" in cb["result_data"]

    async def test_callback_progress_schema(
        self, http_client, service_headers, callback_capture
    ):
        """Progress callbacks should have node-level status updates."""
        payload = make_dispatch_payload(
            manifest=CONTENT_STRATEGY_MANIFEST,
            callback_url="http://host.docker.internal:9999/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        # Wait for all callbacks (running + completed at minimum)
        callbacks = await callback_capture.wait_for_callbacks(2, timeout=20)

        # All callbacks should have a progress dict
        for cb in callbacks:
            if "progress" in cb:
                progress = cb["progress"]
                assert isinstance(progress, dict)
                # Each node entry should have a status
                for node_id, node_progress in progress.items():
                    assert "status" in node_progress
                    assert node_progress["status"] in (
                        "pending",
                        "running",
                        "done",
                        "failed",
                    )

    async def test_callback_failed_schema(
        self, http_client, service_headers, callback_capture
    ):
        """Dispatch with an invalid manifest should produce a 'failed' callback."""
        bad_manifest = {
            "nodes": [
                {"id": "a", "type": "internal", "handler": "NonExistentNode"},
            ],
            "edges": [],
            "global_config": {},
        }
        payload = make_dispatch_payload(
            manifest=bad_manifest,
            callback_url="http://host.docker.internal:9999/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        callbacks = await callback_capture.wait_for_callbacks(2, timeout=15)

        failed = [c for c in callbacks if c.get("status") == "failed"]
        assert len(failed) >= 1, f"No failed callback found in: {callbacks}"

        cb = failed[0]
        assert "error_message" in cb
        assert isinstance(cb["error_message"], str)
        assert "progress" in cb

    async def test_callback_resolved_manifest_schema(
        self, http_client, service_headers, callback_capture
    ):
        """Auto-detect mode sends a resolved_manifest_id callback."""
        payload = make_dispatch_payload(
            manifest=None,
            available_manifests=ALL_AVAILABLE_MANIFESTS,
            callback_url="http://host.docker.internal:9999/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        # Auto-detect: running -> progress (router) ->
        # resolved_manifest -> ... -> completed
        callbacks = await callback_capture.wait_for_callbacks(3, timeout=30)

        resolved = [c for c in callbacks if "resolved_manifest_id" in c]
        assert len(resolved) >= 1, f"No resolved_manifest callback in: {callbacks}"

        cb = resolved[0]
        assert isinstance(cb["resolved_manifest_id"], str)
        assert len(cb["resolved_manifest_id"]) > 0
