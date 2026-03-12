"""Tests for SKL-CIA-06: Market Share Estimator."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.market_share_estimator import MarketShareEstimator
from app.skills.models import SkillContext


def _make_skill(search_results=None):
    tavily = MagicMock()
    if search_results is None:
        search_results = [
            {
                "title": "Acme Corp Company Info",
                "url": "https://linkedin.com/company/acme",
                "content": "Acme Corp has 500 employees and raised $50M in funding.",
            }
        ]
    tavily.search = AsyncMock(return_value=search_results)
    return MarketShareEstimator(tavily)


def _context():
    return SkillContext(session_id="s1", tenant_id="t1")


class TestMarketShareEstimator:
    async def test_meta_skill_id(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-CIA-06"

    async def test_estimates_share(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        assert result.success
        shares = result.data["market_shares"]
        assert len(shares) == 1
        assert shares[0]["slug"] == "acme"

    async def test_extracts_employee_count(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        proxies = result.data["market_shares"][0]["proxies"]
        assert "employee_count" in proxies
        assert proxies["employee_count"] == 500

    async def test_extracts_funding(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        proxies = result.data["market_shares"][0]["proxies"]
        assert "funding" in proxies

    async def test_uses_mra_market_sizing(self):
        skill = _make_skill([])
        result = await skill.execute(
            {
                "competitors": [{"name": "Acme", "slug": "acme"}],
                "industry_context": {
                    "market_sizing": {"tam": {"value": "$50B"}},
                },
            },
            _context(),
        )
        assert result.success
        assert result.data["market_sizing_available"] is True

    async def test_empty_competitors(self):
        skill = _make_skill()
        result = await skill.execute({"competitors": []}, _context())
        assert result.success
        assert result.data["competitors_analyzed"] == 0
