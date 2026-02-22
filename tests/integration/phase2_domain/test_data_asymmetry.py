"""Domain tests: Missing/partial data handling across pipeline.

Verifies the pipeline degrades gracefully when input data is incomplete,
using stub fallbacks and partial scoring.
"""

import pytest

from tests.integration.conftest import (
    INTELLIGENCE_URL,
    ISO_BRAND_EQUITY_MANIFEST,
    ORCHESTRATOR_URL,
    make_agent_payload,
    make_dispatch_payload,
)


@pytest.mark.integration
class TestDataAsymmetry:
    """Pipeline behavior with missing or partial data."""

    async def test_empty_input_context(
        self, http_client, service_headers, callback_capture
    ):
        """Pipeline completes with empty input_context (stub defaults)."""
        payload = make_dispatch_payload(
            manifest=ISO_BRAND_EQUITY_MANIFEST,
            input_prompt="Data asymmetry: empty context pipeline",
            callback_url="http://host.docker.internal:9998/callback",
        )
        payload["input_context"] = {}

        resp = await http_client.post(
            f"{ORCHESTRATOR_URL}/v1/jobs/dispatch",
            json=payload,
            headers=service_headers,
        )
        assert resp.status_code == 202

        completed = await callback_capture.wait_for_completed(timeout=30)
        assert completed is not None, "Pipeline should complete even with empty context"
        assert completed["status"] == "completed"

    async def test_discovery_returns_no_findings(self, http_client, tenant_headers):
        """Intelligence still produces valid BSI when discovery has no useful data."""
        payload = make_agent_payload(
            input_prompt="Data asymmetry: no discovery findings",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "query": "empty search",
                    "sources": [],
                    "findings": [],
                    "recommendations": [],
                    "raw_context": "",
                }
            },
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        bsi = data["bsi"]
        # Should still produce a valid BSI with stub data
        assert 0 <= bsi["score"] <= 100
        assert data["valuation"]["brand_value_npv"] > 0

    async def test_partial_behavioral_data(self, http_client, tenant_headers):
        """Only sentiment_score provided in previous_outputs -> behavioral scored."""
        payload = make_agent_payload(
            input_prompt="Data asymmetry: partial behavioral via sentiment",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "sentiment_score": 75.0,
                    "findings": [],
                }
            },
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        bsi = data["bsi"]
        # Behavioral pillar should be detected via sentiment_score
        assert bsi["data_completeness"] == pytest.approx(0.33, abs=0.01)
        assert bsi["score"] > 0

    async def test_revenue_extracted_from_discovery_text(
        self, http_client, tenant_headers
    ):
        """Discovery findings containing '$51.2 billion' -> intelligence uses it."""
        payload = make_agent_payload(
            input_prompt="Data asymmetry: revenue extraction from text",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "findings": [
                        "Nike reported revenue of $51.2 billion in fiscal year 2023.",
                        "Brand value rankings place Nike in top 10 globally.",
                    ],
                    "raw_context": (
                        "Nike revenue of $51.2 billion. "
                        "Strong brand equity in athletic wear market."
                    ),
                    "sources": [],
                    "recommendations": [],
                }
            },
        )
        # Don't provide projected_revenues — force extraction from text
        payload["input_context"] = {"sector": "retail"}

        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        val = data["valuation"]

        # NPV should be based on ~$51.2B revenue, not the $10M stub
        # With retail rate (3%), 5yr, 10% discount:
        # Year 1 royalty alone: $51.2B * 0.03 * 0.75 / 1.10 = ~$1.047B
        # So NPV should be > $1B (much larger than stub $10M case)
        assert val["brand_value_npv"] > 1_000_000_000, (
            f"NPV {val['brand_value_npv']:.2f} too low"
            " — revenue extraction may have failed"
        )
