"""Tests for SKL-CIA-02: Competitor Website Profiler."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.competitor_website_profiler import CompetitorWebsiteProfiler
from app.skills.models import SkillContext


def _make_skill(scrape_result=None):
    scraper = MagicMock()
    if scrape_result is None:
        scrape_result = {
            "url": "https://acme.com",
            "title": "Acme Corp - AI Tools",
            "content": "Acme provides powerful AI tools. Easy to use platform. Plans starting at $29/month.",
            "status_code": 200,
        }
    scraper.scrape_page = AsyncMock(return_value=scrape_result)
    return CompetitorWebsiteProfiler(scraper)


def _context():
    return SkillContext(session_id="s1", tenant_id="t1")


class TestWebsiteProfiler:
    async def test_meta_skill_id(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-CIA-02"

    async def test_profiles_competitor_website(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert result.success
        profiles = result.data["profiles"]
        assert len(profiles) == 1
        assert profiles[0]["slug"] == "acme"
        assert profiles[0]["name"] == "Acme"

    async def test_handles_no_website(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "NoSite", "slug": "nosite", "website": ""}]},
            _context(),
        )
        assert result.success
        assert "No website" in result.data["profiles"][0]["summary"]

    async def test_empty_competitors_list(self):
        skill = _make_skill()
        result = await skill.execute({"competitors": []}, _context())
        assert result.success
        assert result.data["competitors_processed"] == 0

    async def test_extracts_value_propositions(self):
        scrape_result = {
            "url": "https://acme.com",
            "title": "Acme - Best AI Tool",
            "content": "Transform your brand with AI.\nPowerful analytics dashboard.\nEnterprise-grade security.",
            "status_code": 200,
        }
        skill = _make_skill(scrape_result)
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        profile = result.data["profiles"][0]
        assert len(profile["value_propositions"]) > 0

    async def test_collects_sources(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme", "website": "https://acme.com"}]},
            _context(),
        )
        assert len(result.data["sources"]) > 0
