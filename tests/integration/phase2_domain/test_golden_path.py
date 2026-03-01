"""Domain tests: Full pipeline golden path execution.

Dispatches jobs to the orchestrator and captures callbacks to verify
the complete lifecycle: running -> progress -> completed.
"""

import pytest

from tests.integration.conftest import (
    BRAND_ANALYSIS_MANIFEST,
    CONTENT_STRATEGY_MANIFEST,
    ISO_BRAND_EQUITY_MANIFEST,
    ORCHESTRATOR_URL,
    make_dispatch_payload,
)


@pytest.mark.integration
class TestGoldenPath:
    """Full pipeline dispatch -> callback -> result verification."""

    async def test_brand_analysis_golden_path(
        self, http_client, service_headers, callback_capture
    ):
        """brand-analysis: dispatch -> completed with findings."""
        payload = make_dispatch_payload(
            manifest=BRAND_ANALYSIS_MANIFEST,
            callback_url="http://host.docker.internal:9998/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed(timeout=30)
        assert (
            completed is not None
        ), f"Pipeline did not complete. Callbacks: {callback_capture.callbacks}"

        result_data = completed["result_data"]
        assert "findings" in result_data
        assert len(result_data["findings"]) > 0
        assert "recommendations" in result_data

        # Progress should show all 4 nodes as done
        progress = completed["progress"]
        for node_id in [
            "intent_router",
            "market_research",
            "brand_strategist",
            "report_generator",
        ]:
            assert node_id in progress, f"Node {node_id} missing from progress"
            assert progress[node_id]["status"] == "done", (
                f"Node {node_id} status is"
                f" {progress[node_id]['status']}, expected 'done'"
            )

    async def test_iso_brand_equity_golden_path(
        self, http_client, service_headers, callback_capture
    ):
        """iso-brand-equity: completed with BSI score > 0 and NPV > 0."""
        payload = make_dispatch_payload(
            manifest=ISO_BRAND_EQUITY_MANIFEST,
            callback_url="http://host.docker.internal:9998/callback",
        )
        # Provide financial data so valuation works without Gemini
        payload["input_context"].update(
            {
                "company_name": "TestCorp",
                "sector": "technology",
                "base_revenue": 1_000_000_000,
                "growth_rate": 0.08,
                "profit_margin": 0.15,
                "brand_awareness": 70,
            }
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed(timeout=30)
        assert (
            completed is not None
        ), f"Pipeline did not complete. Callbacks: {callback_capture.callbacks}"

        result_data = completed["result_data"]
        assert "findings" in result_data

        # BSI score should be present and positive (ManagerNode extracts it)
        score = result_data.get("score")
        assert score is not None and score > 0, f"BSI score should be > 0, got: {score}"

        # Valuation NPV should be present and positive
        valuation = result_data.get("valuation")
        if valuation is not None:
            assert valuation.get("brand_value_npv", 0) > 0

    async def test_content_strategy_golden_path(
        self, http_client, service_headers, callback_capture
    ):
        """content-strategy: all-internal pipeline completes without external calls."""
        payload = make_dispatch_payload(
            manifest=CONTENT_STRATEGY_MANIFEST,
            callback_url="http://host.docker.internal:9998/callback",
        )
        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed(timeout=20)
        assert (
            completed is not None
        ), f"Pipeline did not complete. Callbacks: {callback_capture.callbacks}"

        result_data = completed["result_data"]
        assert "findings" in result_data
        assert "recommendations" in result_data

        # All 4 internal nodes should be done
        progress = completed["progress"]
        for node_id in [
            "intent_router",
            "audience_analyzer",
            "content_planner",
            "calendar_builder",
        ]:
            assert node_id in progress
            assert progress[node_id]["status"] == "done"
