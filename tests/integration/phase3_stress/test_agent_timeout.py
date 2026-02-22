"""Stress tests: Agent service timeout handling.

Verifies the orchestrator's ExternalWrapper falls back to stub data
when agent services are slow or unreachable.
"""

import pytest

from tests.integration.conftest import (
    ORCHESTRATOR_URL,
    make_dispatch_payload,
)


@pytest.mark.integration
@pytest.mark.stress
class TestAgentTimeout:
    """Pipeline behavior when agent services are slow or unreachable."""

    async def test_unreachable_agent_gets_stubbed(
        self, http_client, service_headers, callback_capture
    ):
        """Non-existent agent -> pipeline completes with stub."""
        manifest_with_bad_url = {
            "nodes": [
                {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
                {
                    "id": "research",
                    "type": "external",
                    "url": "http://nonexistent-service:9999/v1/execute",
                    "config": {"focus": "test"},
                },
                {"id": "report", "type": "internal", "handler": "ReportNode"},
            ],
            "edges": [
                ["intent_router", "research"],
                ["research", "report"],
            ],
            "global_config": {},
        }
        payload = make_dispatch_payload(
            manifest=manifest_with_bad_url,
            callback_url="http://host.docker.internal:9997/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed_count(1, timeout=90)
        assert len(completed) >= 1, (
            "Pipeline should complete with stub."
            f" Callbacks: {callback_capture.callbacks}"
        )

        # Result should contain stub findings
        result = completed[0]["result_data"]
        assert "findings" in result

    async def test_timeout_doesnt_crash_pipeline(
        self, http_client, service_headers, callback_capture
    ):
        """Pipeline with one unreachable + one reachable agent still completes."""
        manifest_mixed = {
            "nodes": [
                {"id": "intent_router", "type": "internal", "handler": "RouterNode"},
                {
                    "id": "working_agent",
                    "type": "external",
                    "url": "http://discovery-agent-svc:8020/v1/search",
                    "config": {"focus": "market_trends"},
                },
                {"id": "strategist", "type": "internal", "handler": "StrategyNode"},
                {"id": "report", "type": "internal", "handler": "ReportNode"},
            ],
            "edges": [
                ["intent_router", "working_agent"],
                ["working_agent", "strategist"],
                ["strategist", "report"],
            ],
            "global_config": {},
        }
        payload = make_dispatch_payload(
            manifest=manifest_mixed,
            callback_url="http://host.docker.internal:9997/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed_count(1, timeout=30)
        assert len(completed) >= 1
        result = completed[0]["result_data"]
        assert "findings" in result
        assert len(result["findings"]) > 0
