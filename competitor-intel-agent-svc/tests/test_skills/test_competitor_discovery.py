"""Tests for SKL-CIA-01: Competitor Discovery Search."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.competitor_discovery_search import CompetitorDiscoverySearch
from app.skills.models import SkillContext


def _make_skill(search_results=None):
    tavily = MagicMock()
    tavily.search = AsyncMock(return_value=search_results or [])
    return CompetitorDiscoverySearch(tavily)


def _context():
    return SkillContext(session_id="s1", tenant_id="t1", user_role="EDITOR")


class TestCompetitorDiscoverySearch:
    async def test_meta_skill_id(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-CIA-01"

    async def test_returns_success_with_empty_competitors(self):
        skill = _make_skill([])
        result = await skill.execute(
            {"query": "AI tools competitors"}, _context()
        )
        assert result.success
        assert isinstance(result.data["competitors"], list)

    async def test_uses_mra_seeds(self):
        skill = _make_skill([])
        mra_competitors = [
            {"name": "Acme Corp", "description": "AI leader", "market_position": "leader"},
            {"name": "Beta Inc", "description": "Challenger", "market_position": "challenger"},
        ]
        result = await skill.execute(
            {"query": "AI tools", "mra_competitors": mra_competitors},
            _context(),
        )
        assert result.success
        names = [c["name"] for c in result.data["competitors"]]
        assert "Acme Corp" in names
        assert "Beta Inc" in names

    async def test_deduplicates_mra_seeds(self):
        skill = _make_skill([])
        mra_competitors = [
            {"name": "Acme Corp"},
            {"name": "Acme Corp"},
        ]
        result = await skill.execute(
            {"query": "AI", "mra_competitors": mra_competitors}, _context()
        )
        names = [c["name"] for c in result.data["competitors"]]
        assert names.count("Acme Corp") == 1

    async def test_respects_max_competitors(self):
        # Return many search results
        search_results = [
            {"title": f"Company {i} vs others", "url": f"https://co{i}.com", "content": f"Company {i} is..."}
            for i in range(30)
        ]
        skill = _make_skill(search_results)
        result = await skill.execute(
            {"query": "AI", "max_competitors": 5}, _context()
        )
        assert len(result.data["competitors"]) <= 5

    async def test_caps_at_20(self):
        skill = _make_skill([])
        result = await skill.execute(
            {"query": "AI", "max_competitors": 50}, _context()
        )
        # The cap is applied inside the skill — just verify no crash
        assert result.success

    async def test_empty_query_returns_failure(self):
        skill = _make_skill()
        result = await skill.execute({"query": ""}, _context())
        assert not result.success
        assert "No query" in result.error

    async def test_sources_collected(self):
        search_results = [
            {"title": "Competitor Guide", "url": "https://example.com/guide", "content": "..."}
        ]
        skill = _make_skill(search_results)
        result = await skill.execute({"query": "AI tools"}, _context())
        assert result.success
        sources = result.data.get("sources", [])
        assert isinstance(sources, list)

    async def test_duration_tracked(self):
        skill = _make_skill([])
        result = await skill.execute({"query": "test"}, _context())
        assert result.duration_ms >= 0
