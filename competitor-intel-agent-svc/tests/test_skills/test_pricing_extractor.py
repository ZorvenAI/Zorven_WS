"""Tests for SKL-CIA-05: Pricing Strategy Extractor."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.pricing_strategy_extractor import PricingStrategyExtractor
from app.skills.models import SkillContext


def _make_skill(scrape_result=None, search_results=None):
    scraper = MagicMock()
    if scrape_result is None:
        scrape_result = {
            "url": "https://acme.com/pricing",
            "title": "Acme Pricing",
            "content": (
                "Starter plan: $29/month. Pro plan: $99/month. "
                "Enterprise: contact us. Free plan available."
            ),
            "status_code": 200,
        }
    scraper.scrape_page = AsyncMock(return_value=scrape_result)

    tavily = MagicMock()
    tavily.search = AsyncMock(return_value=search_results or [])

    return PricingStrategyExtractor(scraper, tavily)


def _context():
    return SkillContext(session_id="s1", tenant_id="t1")


class TestPricingExtractor:
    async def test_meta_skill_id(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-CIA-05"

    async def test_extracts_pricing(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert result.success
        pricing = result.data["pricing_data"]
        assert len(pricing) == 1
        assert pricing[0]["slug"] == "acme"

    async def test_detects_subscription_model(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert result.data["pricing_data"][0]["model_type"] == "subscription"

    async def test_detects_free_tier(self):
        scrape_result = {
            "url": "https://acme.com/pricing",
            "title": "Pricing",
            "content": "Free plan forever. Starter at $29/month.",
            "status_code": 200,
        }
        skill = _make_skill(scrape_result)
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert result.data["pricing_data"][0]["has_free_tier"] is True

    async def test_detects_enterprise(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert result.data["pricing_data"][0]["has_enterprise"] is True

    async def test_fallback_to_tavily_search(self):
        scraper = MagicMock()
        scraper.scrape_page = AsyncMock(return_value={
            "url": "", "title": "", "content": "", "status_code": 404,
        })
        tavily = MagicMock()
        tavily.search = AsyncMock(return_value=[
            {
                "title": "Acme Pricing",
                "url": "https://review.com/acme-pricing",
                "content": "Acme charges $49/month for their pro plan.",
            }
        ])
        skill = PricingStrategyExtractor(scraper, tavily)
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert result.success

    async def test_empty_competitors(self):
        skill = _make_skill()
        result = await skill.execute({"competitors": []}, _context())
        assert result.success
        assert result.data["competitors_analyzed"] == 0
