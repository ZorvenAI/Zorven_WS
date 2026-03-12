"""Tests for SKL-CIA-04: Customer Review Aggregator."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.customer_review_aggregator import CustomerReviewAggregator
from app.skills.models import SkillContext


def _make_skill(search_results=None):
    tavily = MagicMock()
    if search_results is None:
        search_results = [
            {
                "title": "Acme Corp Reviews - G2",
                "url": "https://www.g2.com/products/acme",
                "content": "Acme is rated 4.5/5 stars. Users love the easy to use interface. Some find it expensive.",
            },
            {
                "title": "Acme Reviews - Capterra",
                "url": "https://www.capterra.com/p/acme",
                "content": "4.2 out of 5 stars. Powerful features but slow support.",
            },
        ]
    tavily.search = AsyncMock(return_value=search_results)
    return CustomerReviewAggregator(tavily)


def _context():
    return SkillContext(session_id="s1", tenant_id="t1")


class TestReviewAggregator:
    async def test_meta_skill_id(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-CIA-04"

    async def test_aggregates_reviews(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        assert result.success
        reviews = result.data["reviews"]
        assert len(reviews) == 1
        assert reviews[0]["slug"] == "acme"

    async def test_extracts_rating(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        avg = result.data["reviews"][0]["avg_rating"]
        assert avg is not None
        assert 1.0 <= avg <= 5.0

    async def test_detects_review_sources(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        review_sources = result.data["reviews"][0]["review_sources"]
        assert "g2.com" in review_sources or "capterra.com" in review_sources

    async def test_extracts_praise_themes(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        praises = result.data["reviews"][0]["top_praise_themes"]
        assert len(praises) > 0

    async def test_extracts_complaint_themes(self):
        skill = _make_skill()
        result = await skill.execute(
            {"competitors": [{"name": "Acme", "slug": "acme"}]},
            _context(),
        )
        complaints = result.data["reviews"][0]["top_complaint_themes"]
        assert len(complaints) > 0

    async def test_empty_competitors(self):
        skill = _make_skill()
        result = await skill.execute({"competitors": []}, _context())
        assert result.success
        assert result.data["competitors_analyzed"] == 0
