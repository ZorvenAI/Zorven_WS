"""Contract tests: Orchestrator -> Intelligence agent service.

Direct HTTP calls to intelligence-agent-svc validating the ExecuteRequest
/ ExecuteResponse contract for ISO valuation and gap analysis.
"""

import pytest

from tests.integration.conftest import (
    INTELLIGENCE_URL,
    make_agent_payload,
)


@pytest.mark.integration
class TestIntelligenceContract:
    """POST /v1/execute, /v1/iso-calc, /v1/analyze contract validation."""

    async def test_iso_calc_returns_valuation_and_bsi(
        self, http_client, tenant_headers
    ):
        """POST /v1/iso-calc returns valuation and BSI objects."""
        payload = make_agent_payload(
            config={"method": "royalty_relief", "horizon_years": 5},
        )
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Required fields
        assert "findings" in data
        assert "recommendations" in data
        assert isinstance(data["findings"], list)
        assert isinstance(data["recommendations"], list)

        # Valuation-specific fields
        assert "valuation" in data
        assert data["valuation"] is not None
        val = data["valuation"]
        assert "brand_value_npv" in val
        assert isinstance(val["brand_value_npv"], (int, float))
        assert val["brand_value_npv"] > 0

        # BSI fields
        assert "bsi" in data
        assert data["bsi"] is not None
        bsi = data["bsi"]
        assert "score" in bsi
        assert isinstance(bsi["score"], int)
        assert 0 <= bsi["score"] <= 100

    async def test_analyze_returns_gap_analysis(self, http_client, tenant_headers):
        """POST /v1/analyze returns findings and recommendations."""
        payload = make_agent_payload(
            config={"analysis_type": "competitive_gap"},
            previous_outputs={
                "competitor_research": {
                    "findings": [
                        "Alpha Corp leads with 30% market share.",
                        "Beta Inc is growing at 15% annually.",
                    ],
                    "sources": [
                        {
                            "type": "web",
                            "title": "Report",
                            "url": "https://example.com",
                        },
                    ],
                }
            },
        )
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/analyze",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "findings" in data
        assert "recommendations" in data
        assert len(data["findings"]) > 0

    async def test_execute_routes_by_config_method(self, http_client, tenant_headers):
        """config.method='royalty_relief' triggers ISO valuation path."""
        payload = make_agent_payload(
            config={"method": "royalty_relief"},
        )
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/execute",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have valuation data from ISO path
        assert (
            data.get("valuation") is not None
            or data.get("methodology") == "royalty_relief"
        )

    async def test_execute_routes_by_analysis_type(self, http_client, tenant_headers):
        """config.analysis_type='competitive_gap' triggers gap analysis."""
        payload = make_agent_payload(
            config={"analysis_type": "competitive_gap"},
        )
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/execute",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "findings" in data

    async def test_bsi_schema_has_pillars(self, http_client, tenant_headers):
        """BSI pillars are a list of {name, weight, score, rationale}."""
        payload = make_agent_payload(
            config={"method": "royalty_relief"},
        )
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        bsi = data.get("bsi")
        assert bsi is not None
        pillars = bsi.get("pillars", [])
        assert isinstance(pillars, list)
        assert len(pillars) > 0

        for pillar in pillars:
            assert "name" in pillar
            assert "weight" in pillar
            assert "score" in pillar
            assert isinstance(pillar["name"], str)
            assert isinstance(pillar["weight"], (int, float))
            assert isinstance(pillar["score"], (int, float))
            assert 0 <= pillar["score"] <= 100

    async def test_valuation_schema_has_npv(self, http_client, tenant_headers):
        """Valuation object has brand_value_npv as positive float."""
        payload = make_agent_payload(
            config={"method": "royalty_relief", "horizon_years": 5},
        )
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        val = data.get("valuation")
        assert val is not None
        assert "brand_value_npv" in val
        assert isinstance(val["brand_value_npv"], (int, float))
        assert val["brand_value_npv"] > 0
        assert "royalty_rate" in val
        assert "discount_rate" in val
        assert "tax_rate" in val
        assert "horizon_years" in val
        assert "annual_royalties" in val
        assert isinstance(val["annual_royalties"], list)
