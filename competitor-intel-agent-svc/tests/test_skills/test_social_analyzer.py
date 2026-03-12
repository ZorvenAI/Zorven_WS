"""Tests for SKL-CIA-03: Social Media Analyzer."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.social_media_analyzer import SocialMediaAnalyzer
from app.skills.models import SkillContext


def _make_skill(search_results=None):
    tavily = MagicMock()
    if search_results is None:
        search_results = [
            {
                "title": "Acme Corp LinkedIn",
                "url": "https://linkedin.com/company/acme",
                "content": "Acme has 10K followers and posts educational content weekly.",
            },
            {
                "title": "Acme on Twitter",
                "url": "https://twitter.com/acme",
                "content": "Acme announces new feature release.",
            },
        ]
    tavily.search = AsyncMock(return_value=search_results)
    return SocialMediaAnalyzer(tavily)


def _context():
    return SkillContext(session_id="s1", tenant_id="t1")


class TestSocialMediaAnalyzer:
    async def test_meta_skill_id(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-CIA-03"

    async def test_analyzes_competitor_social(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        assert result.success
        social = result.data["social_data"]
        assert len(social) == 1
        assert social[0]["slug"] == "acme"
        assert social[0]["platform_count"] >= 1

    async def test_detects_platforms(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        platforms = result.data["social_data"][0]["platforms"]
        assert "linkedin" in platforms or "twitter" in platforms

    async def test_empty_competitors(self):
        skill = _make_skill()
        result = await skill.execute({"competitors": []}, _context())
        assert result.success
        assert result.data["competitors_analyzed"] == 0

    async def test_extracts_content_themes(self):
        results = [
            {
                "title": "Acme Content",
                "url": "https://linkedin.com/acme",
                "content": "Learn how to build brands. New tips and guide for your business.",
            }
        ]
        skill = _make_skill(results)
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        themes = result.data["social_data"][0]["content_themes"]
        assert "educational" in themes

    async def test_includes_freshness_warning(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        warning = result.data["social_data"][0]["data_freshness_warning"].lower()
        assert "real-time" in warning or "not reflect" in warning
