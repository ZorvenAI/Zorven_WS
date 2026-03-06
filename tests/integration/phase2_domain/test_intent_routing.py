"""Domain tests: Auto-detect intent routing accuracy.

Dispatches jobs without a manifest and verifies the RouterNode
resolves to the correct pipeline based on input_prompt keywords.
"""

import pytest

from tests.integration.conftest import (
    ALL_AVAILABLE_MANIFESTS,
    ORCHESTRATOR_URL,
    make_dispatch_payload,
)


@pytest.mark.integration
class TestIntentRouting:
    """Validate intent routing resolves correct manifest."""

    async def _dispatch_auto_detect(
        self, http_client, service_headers, callback_capture, input_prompt: str
    ) -> dict:
        """Helper: dispatch auto-detect job, return callbacks."""
        payload = make_dispatch_payload(
            manifest=None,
            input_prompt=input_prompt,
            available_manifests=ALL_AVAILABLE_MANIFESTS,
            callback_url="http://host.docker.internal:9998/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        # Wait for resolved_manifest callback
        await callback_capture.wait_for_callbacks(3, timeout=30)
        resolved = [
            c for c in callback_capture.callbacks if "resolved_manifest_id" in c
        ]
        return resolved[0] if resolved else {}

    async def test_brand_keywords_resolve_brand_analysis(
        self, http_client, service_headers, callback_capture
    ):
        """'brand positioning market analysis' -> brand-analysis."""
        result = await self._dispatch_auto_detect(
            http_client,
            service_headers,
            callback_capture,
            "Analyze brand positioning and market analysis for Acme Corp",
        )
        assert result.get("resolved_manifest_id") == "brand-analysis"

    async def test_competitor_keywords_resolve_competitor_audit(
        self, http_client, service_headers, callback_capture
    ):
        """'competitor audit gap analysis' -> competitor-audit."""
        result = await self._dispatch_auto_detect(
            http_client,
            service_headers,
            callback_capture,
            "Run a competitor audit and gap analysis",
        )
        assert result.get("resolved_manifest_id") == "competitor-audit"

    async def test_content_keywords_resolve_content_strategy(
        self, http_client, service_headers, callback_capture
    ):
        """'content strategy editorial calendar' -> content-strategy."""
        result = await self._dispatch_auto_detect(
            http_client,
            service_headers,
            callback_capture,
            "Create a content strategy and editorial calendar",
        )
        assert result.get("resolved_manifest_id") == "content-strategy"

    async def test_ambiguous_prompt_defaults_general_chat(
        self, http_client, service_headers, callback_capture
    ):
        """Ambiguous input -> defaults to general-chat (neutral default)."""
        result = await self._dispatch_auto_detect(
            http_client,
            service_headers,
            callback_capture,
            "Do something interesting with data",
        )
        assert result.get("resolved_manifest_id") == "general-chat"

    async def test_routing_plus_execution(
        self, http_client, service_headers, callback_capture
    ):
        """Auto-detect routes AND executes the resolved pipeline to completion."""
        payload = make_dispatch_payload(
            manifest=None,
            input_prompt="Analyze brand positioning for Acme Corp",
            available_manifests=ALL_AVAILABLE_MANIFESTS,
            callback_url="http://host.docker.internal:9998/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed(timeout=30)
        assert completed is not None, (
            "Auto-detect pipeline should complete."
            f" Callbacks: {callback_capture.callbacks}"
        )

        # Should have real pipeline results, not just routing metadata
        result_data = completed["result_data"]
        assert "findings" in result_data
        assert len(result_data["findings"]) > 0
        # Should NOT contain "auto-detect" or routing-only messages
        for finding in result_data["findings"]:
            assert "auto-detect" not in finding.lower()
