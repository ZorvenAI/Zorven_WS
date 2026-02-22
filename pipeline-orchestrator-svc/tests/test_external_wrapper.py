"""Tests for ExternalWrapper — HTTP calls to external agent services."""

import pytest

from app.nodes.external_wrapper import ExternalWrapper
from app.state.schema import AgentState


def _base_state() -> AgentState:
    return {
        "job_id": "test-job",
        "tenant_id": "1",
        "input_prompt": "Analyze brand",
        "input_context": {"company_id": 42},
        "tenant_context": {"tenant_id": "1"},
        "global_config": {},
        "callback_url": "http://localhost:8001/callback/",
        "available_manifests": None,
        "resolved_manifest_id": None,
        "node_outputs": {},
        "progress": {},
        "result_data": None,
        "error": None,
        "cancelled": False,
    }


class TestExternalWrapper:
    async def test_successful_http_call(self, httpx_mock):
        """External service returns valid JSON."""
        httpx_mock.add_response(
            url="http://discovery-agent-svc:8020/v1/search",
            method="POST",
            json={"analysis": "market trends found", "findings": ["Trend A"]},
        )

        wrapper = ExternalWrapper(
            url="http://discovery-agent-svc:8020/v1/search",
            node_id="web_research",
        )
        result = await wrapper(_base_state())

        outputs = result.get("node_outputs", {})
        assert "web_research" in outputs
        assert outputs["web_research"]["analysis"] == "market trends found"

    async def test_sends_tenant_id_header(self, httpx_mock):
        """Request includes X-Tenant-ID header from tenant_context."""
        httpx_mock.add_response(
            url="http://discovery-agent-svc:8020/v1/search",
            method="POST",
            json={"result": "ok"},
        )

        wrapper = ExternalWrapper(
            url="http://discovery-agent-svc:8020/v1/search",
            node_id="web_research",
        )
        await wrapper(_base_state())

        request = httpx_mock.get_request()
        assert request.headers["X-Tenant-ID"] == "1"

    async def test_fallback_on_connection_error(self, httpx_mock):
        """On HTTP error, returns stub data instead of raising."""
        import httpx

        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="http://unreachable-service/v1/analyze",
        )

        wrapper = ExternalWrapper(
            url="http://unreachable-service/v1/analyze",
            node_id="gap_analyzer",
        )
        result = await wrapper(_base_state())

        outputs = result.get("node_outputs", {})
        assert "gap_analyzer" in outputs
        assert outputs["gap_analyzer"]["status"] == "stub"

    async def test_fallback_on_500_error(self, httpx_mock):
        """On 5xx response, returns stub data."""
        httpx_mock.add_response(
            url="http://discovery-agent-svc:8020/v1/search",
            method="POST",
            status_code=500,
        )

        wrapper = ExternalWrapper(
            url="http://discovery-agent-svc:8020/v1/search",
            node_id="web_research",
        )
        result = await wrapper(_base_state())

        outputs = result.get("node_outputs", {})
        assert "web_research" in outputs
        assert outputs["web_research"]["status"] == "stub"
