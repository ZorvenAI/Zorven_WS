"""Domain tests: BSI (Brand Strength Index) multi-pillar scoring.

BSI Pillars: Financial (40%), Behavioral (35%), Legal (25%).
ProxyEngine redistributes weights when pillars are missing.

Note: Financial data is sourced from GCS (unavailable in stub mode).
Only behavioral (via previous_outputs) and legal (via input_context) can be
provided through the API. Max achievable data_completeness in tests = 0.67.
"""

import pytest

from tests.integration.conftest import (
    INTELLIGENCE_URL,
    make_agent_payload,
)


@pytest.mark.integration
class TestBSIScoring:
    """Validate BSI scoring logic via intelligence-agent-svc."""

    async def test_behavioral_and_legal_bsi(self, http_client, tenant_headers):
        """Behavioral + Legal provided -> 2 pillars, completeness=0.67."""
        payload = make_agent_payload(
            input_prompt="BSI test: behavioral + legal pillars",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "behavioral_data": {
                        "brand_awareness": 80,
                        "sentiment_score": 75,
                        "customer_loyalty": 70,
                    },
                    "findings": ["Strong brand presence in market."],
                }
            },
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
            "sector": "technology",
            "legal_data": {
                "trademark_strength": 85,
                "geographic_coverage": 60,
            },
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        bsi = data["bsi"]

        assert bsi["data_completeness"] == pytest.approx(0.67, abs=0.01)
        assert len(bsi["pillars"]) == 2
        assert 0 <= bsi["score"] <= 100

        # Verify pillar weights sum to ~1.0
        total_weight = sum(p["weight"] for p in bsi["pillars"])
        assert total_weight == pytest.approx(1.0, abs=0.01)

    async def test_behavioral_only(self, http_client, tenant_headers):
        """Behavioral only (via previous_outputs) -> 1 pillar, completeness=0.33."""
        payload = make_agent_payload(
            input_prompt="BSI test: behavioral pillar only",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "behavioral_data": {
                        "brand_awareness": 80,
                        "sentiment_score": 75,
                    },
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

        assert bsi["data_completeness"] == pytest.approx(0.33, abs=0.01)
        total_weight = sum(p["weight"] for p in bsi["pillars"])
        assert total_weight == pytest.approx(1.0, abs=0.01)

    async def test_legal_only(self, http_client, tenant_headers):
        """Legal only (via input_context) -> 1 pillar, completeness=0.33."""
        payload = make_agent_payload(
            input_prompt="BSI test: legal pillar only",
            config={"method": "royalty_relief"},
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
            "legal_data": {
                "trademark_strength": 90,
            },
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        bsi = data["bsi"]

        assert bsi["data_completeness"] == pytest.approx(0.33, abs=0.01)
        total_weight = sum(p["weight"] for p in bsi["pillars"])
        assert total_weight == pytest.approx(1.0, abs=0.01)

    async def test_no_data_uses_stubs(self, http_client, tenant_headers):
        """No pillar data -> stub scores, completeness=0.0."""
        payload = make_agent_payload(
            input_prompt="BSI test: no pillar data stubs",
            config={"method": "royalty_relief"},
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

        assert bsi["data_completeness"] == 0.0
        assert bsi["score"] > 0  # Stub scores produce non-zero BSI
        assert bsi["score"] <= 100

    async def test_bsi_score_clamped_0_100(self, http_client, tenant_headers):
        """Extreme inputs never produce score outside 0-100."""
        payload = make_agent_payload(
            input_prompt="BSI test: extreme values clamping",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "behavioral_data": {
                        "brand_awareness": 200,
                        "sentiment_score": 200,
                    },
                }
            },
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
            "legal_data": {"trademark_strength": 200},
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        bsi = resp.json()["bsi"]
        assert 0 <= bsi["score"] <= 100

    async def test_data_completeness_fraction(self, http_client, tenant_headers):
        """0 pillars = 0.0, 1 = 0.33, 2 = 0.67."""
        # 0 pillars
        payload = make_agent_payload(
            input_prompt="BSI test: completeness 0 pillars",
            config={"method": "royalty_relief"},
        )
        payload["input_context"] = {"projected_revenues": [10_000_000]}
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        bsi_0 = resp.json()["bsi"]
        assert bsi_0["data_completeness"] == 0.0

        # 1 pillar: legal only (unique prompt to avoid cache)
        payload_1 = make_agent_payload(
            input_prompt="BSI test: completeness 1 pillar legal",
            config={"method": "royalty_relief"},
        )
        payload_1["input_context"] = {
            "projected_revenues": [10_000_000],
            "legal_data": {"trademark_strength": 80},
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload_1,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        bsi_1 = resp.json()["bsi"]
        assert bsi_1["data_completeness"] == pytest.approx(0.33, abs=0.01)

        # 2 pillars: legal + behavioral (unique prompt)
        payload_2 = make_agent_payload(
            input_prompt="BSI test: completeness 2 pillars",
            config={"method": "royalty_relief"},
            previous_outputs={
                "web_research": {
                    "behavioral_data": {"brand_awareness": 70},
                }
            },
        )
        payload_2["input_context"] = {
            "projected_revenues": [10_000_000],
            "legal_data": {"trademark_strength": 80},
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload_2,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        bsi_2 = resp.json()["bsi"]
        assert bsi_2["data_completeness"] == pytest.approx(0.67, abs=0.01)
