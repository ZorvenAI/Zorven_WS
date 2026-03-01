"""Domain tests: ISO 10668 Royalty Relief NPV accuracy.

Calls intelligence-agent-svc /v1/iso-calc with controlled inputs and
verifies the returned NPV against hand-calculated benchmarks.

Explicit period:
  NPV = Sum[ (Revenue_t x RoyaltyRate x (1 - TaxRate)) / (1 + DiscountRate)^t ]

Terminal value (Gordon Growth Model, g=2.5%):
  TV  = (Final_Royalty x (1 + g)) / (DiscountRate - g)
  Total NPV = Explicit NPV + PV(TV)
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
        """Revenue $10M x 5yr, rate=4%, discount=10%, tax=25%.

        Explicit period:
          Year 1-5: 10,000,000 x 0.04 x 0.75 / 1.10^t -> sum = 1,137,236.01

        Terminal value (g=2.5%):
          TV = (300,000 x 1.025) / (0.10 - 0.025) = 4,100,000.00
          PV(TV) = 4,100,000 / 1.10^5 = 2,545,777.45

        Total NPV = 1,137,236.01 + 2,545,777.45 = 3,683,013.46

        Note: brand_awareness=50 ensures BSI >= 40, avoiding the
        10% royalty rate discount applied to weak brands (BSI < 40).
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
            "brand_awareness": 50,
        }

        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        val = data["valuation"]
        expected_npv = 3_683_013.46
        assert (
            abs(val["brand_value_npv"] - expected_npv) < 5.0
        ), f"NPV {val['brand_value_npv']:.2f} not within $5 of {expected_npv:.2f}"
        assert val["royalty_rate"] == pytest.approx(0.04, abs=0.001)
        assert val["horizon_years"] == 5
        assert len(val["annual_royalties"]) == 5

    async def test_npv_empty_revenues_returns_error(
        self, http_client, tenant_headers
    ):
        """Empty revenue list with no fallback data -> error response."""
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
        # No revenue data → executor returns error (no valuation)
        assert data.get("valuation") is None
        assert "findings" in data
        assert len(data["findings"]) > 0

    async def test_npv_single_year(self, http_client, tenant_headers):
        """One year explicit + terminal value.

        Explicit: $10M x 0.04 x 0.75 / 1.10 = $272,727.27
        TV = (300,000 x 1.025) / (0.10 - 0.025) = $4,100,000.00
        PV(TV) = $4,100,000 / 1.10 = $3,727,272.73
        Total = $4,000,000.00
        """
        payload = make_agent_payload(
            input_prompt="NPV benchmark: single year $10M",
            config={"method": "royalty_relief"},
        )
        payload["input_context"] = {
            "projected_revenues": [10_000_000],
            "sector": "technology",
            "brand_awareness": 50,
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        val = data["valuation"]
        expected = 4_000_000.00
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
            "brand_awareness": 50,
        }
        resp = await http_client.post(
            f"{INTELLIGENCE_URL}/v1/iso-calc",
            json=payload,
            headers=tenant_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        val = data["valuation"]

        # NPV should be higher than flat $10M case (including terminal value)
        flat_npv = 3_683_013.46
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
                "brand_awareness": 50,
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
