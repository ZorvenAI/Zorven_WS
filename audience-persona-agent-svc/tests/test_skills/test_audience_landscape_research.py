"""Tests for SKL-APA-01: Audience Landscape Research."""

from unittest.mock import AsyncMock

from app.skills.audience_landscape_research import AudienceLandscapeResearch
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


def _mock_tavily(results=None):
    client = AsyncMock()
    if results is None:
        results = [
            {
                "title": "Audience Demographics Report",
                "url": "https://example.com/demographics",
                "content": "Target audience demographics include age group 25-45, "
                "income $75k-150k, urban professional consumer segment.",
            },
        ]
    client.search = AsyncMock(return_value=results)
    return client


class TestAudienceLandscapeResearch:
    async def test_meta(self):
        skill = AudienceLandscapeResearch(AsyncMock())
        assert skill.meta.skill_id == "SKL-APA-01"
        assert skill.meta.circuit_breaker_dependency == "tavily"

    async def test_execute_success(self):
        tavily = _mock_tavily()
        skill = AudienceLandscapeResearch(tavily)
        result = await skill.execute({"prompt": "SaaS buyer personas"}, _ctx())
        assert result.success is True
        assert result.skill_id == "SKL-APA-01"
        assert "context" in result.data
        assert "sources" in result.data
        assert "audience_signals" in result.data
        assert tavily.search.call_count >= 1

    async def test_execute_with_mra_context(self):
        tavily = _mock_tavily()
        skill = AudienceLandscapeResearch(tavily)
        result = await skill.execute(
            {
                "prompt": "SaaS personas",
                "mra_context": {
                    "market_overview": "The SaaS market is growing at 15% CAGR."
                },
            },
            _ctx(),
        )
        assert result.success is True
        assert "Market Context" in result.data["context"]

    async def test_execute_empty_prompt(self):
        skill = AudienceLandscapeResearch(AsyncMock())
        result = await skill.execute({"prompt": ""}, _ctx())
        assert result.success is False
        assert "No query" in result.error

    async def test_execute_no_results(self):
        tavily = _mock_tavily(results=[])
        skill = AudienceLandscapeResearch(tavily)
        result = await skill.execute({"prompt": "niche"}, _ctx())
        assert result.success is True
        assert result.data["total_results"] == 0

    async def test_duration_tracked(self):
        tavily = _mock_tavily()
        skill = AudienceLandscapeResearch(tavily)
        result = await skill.execute({"prompt": "test"}, _ctx())
        assert result.duration_ms > 0
