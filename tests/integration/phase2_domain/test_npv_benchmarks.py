"""Domain tests: ISO 10668 Royalty Relief NPV accuracy.

Calls intelligence-agent-svc /v1/iso-calc with controlled inputs and
verifies the returned NPV against hand-calculated benchmarks.

NPV formula:
  NPV = Sum[ (Revenue_t x RoyaltyRate x (1 - TaxRate)) / (1 + DiscountRate)^t ]
"""

import pytest

from tests.integration.conftest import (
    INTELLIGENCE_URL,
    make_agent_payload,
)


@pytest.mark.integration
class TestNPVBenchmarks:
    """Validate Royalty Relief NPV against known calculations."""

    async def test_npv_known_inputs(self, http_client, tenant_headers):
        """Revenue $10M x 5yr, rate=4%, discount=10%, tax=25% -> NPV ~$1,137,236.

        Manual:
          Year 1: 10,000,000 x 0.04 x 0.75 / 1.10^1 = 272,727.27
          Year 2: 10,000,000 x 0.04 x 0.75 / 1.10^2 = 247,933.88
          Year 3: 10,000,000 x 0.04 x 0.75 / 1.10^3 = 225,394.44
          Year 4: 10,000,000 x 0.04 x 0.75 / 1.10^4 = 204,904.03
          Year 5: 10,000,000 x 0.04 x 0.75 / 1.10^5 = 186,276.39
                                                 Total: 1,137,236.01
        """
        payload = make_agent_payload(
            input_prompt="NPV benchmark: 5-year flat $10M technology",
            config={
                "method": "royalty_relief",
                "horizon_years": 5,
            },
        )
        payload["input_context"] = {
            "projected_revenues": [
                10_000_000,
                10_000_000,
                10_000_000,
                10_000_000,
                10_000_000,
            ],
            "sector": "technology",
        }

        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        val = data["valuation"]
        expected_npv = 1_137_236.01
        assert (
            abs(val["brand_value_npv"] - expected_npv) < 5.0
        ), f"NPV {val['brand_value_npv']:.2f} not within $5 of {expected_npv:.2f}"
        assert val["royalty_rate"] == pytest.approx(0.04, abs=0.001)
        assert val["horizon_years"] == 5
        assert len(val["annual_royalties"]) == 5

    async def test_npv_empty_revenues_uses_stub(self, http_client, tenant_headers):
        """Empty revenue list -> engine uses stub $10M projection."""
        payload = make_agent_payload(
            input_prompt="NPV benchmark: empty revenues fallback",
            config={"method": "royalty_relief"},
        )
        payload["input_context"] = {
            "projected_revenues": [],
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        val = data["valuation"]
        # Empty list falls through to stub $10M projection
        assert val["brand_value_npv"] > 0
        assert val["horizon_years"] >= 1

    async def test_npv_single_year(self, http_client, tenant_headers):
        """One year: $10M x 0.04 x 0.75 / 1.10 = $272,727.27."""
        payload = make_agent_payload(
            input_prompt="NPV benchmark: single year $10M",
            config={"method": "royalty_relief"},
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
            "sector": "technology",
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        val = data["valuation"]
        expected = 272_727.27
        assert abs(val["brand_value_npv"] - expected) < 1.0
        assert val["horizon_years"] == 1

    async def test_npv_with_growth(self, http_client, tenant_headers):
        """Revenue growing at 5% from $10M base over 5 years."""
        base = 10_000_000
        growth = 0.05
        revenues = [base * (1 + growth) ** t for t in range(5)]

        payload = make_agent_payload(
            input_prompt="NPV benchmark: 5-year growth revenues",
            config={"method": "royalty_relief"},
        )
        payload["input_context"] = {
            "projected_revenues": revenues,
            "sector": "technology",
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        val = data["valuation"]

        # NPV should be higher than flat $10M case
        flat_npv = 1_137_236.01
        assert val["brand_value_npv"] > flat_npv
        assert val["horizon_years"] == 5

    async def test_sector_royalty_rates(self, http_client, tenant_headers):
        """Different sectors get appropriate royalty rates."""
        expected_rates = {
            "technology": 0.04,
            "luxury": 0.05,
            "retail": 0.03,
        }
        for sector, expected_rate in expected_rates.items():
            payload = make_agent_payload(
                # Unique prompt per sector to avoid result cache collisions
                input_prompt=f"NPV benchmark: sector test for {sector}",
                config={"method": "royalty_relief"},
            )
            payload["input_context"] = {
                "projected_revenues": [10_000_000],
                "sector": sector,
            }
            resp = await http_client.post(
                f"{INTELLIGENCE_URL}/v1/iso-calc",
                json=payload,
                headers=tenant_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            val = data["valuation"]
            assert val["royalty_rate"] == pytest.approx(expected_rate, abs=0.001), (
                f"Sector '{sector}': expected rate"
                f" {expected_rate}, got {val['royalty_rate']}"
            )
