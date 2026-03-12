"""Tests for SKL-MRA-01: WebMarketSearch."""

from unittest.mock import AsyncMock

import pytest

from app.services.api_clients import GNewsClient, TavilySearchClient
from app.skills.models import SkillContext
from app.skills.web_market_search import WebMarketSearch


def _make_skill(tavily_results=None, news_results=None) -> WebMarketSearch:
    tavily = TavilySearchClient("")
    tavily.search = AsyncMock(return_value=tavily_results or [])
    gnews = GNewsClient("")
    gnews.search_news = AsyncMock(return_value=news_results or [])
    return WebMarketSearch(tavily, gnews)


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestWebMarketSearch:
    async def test_success_with_results(self):
        skill = _make_skill(
            tavily_results=[{"title": "T1", "url": "https://a.com", "content": "C1"}],
            news_results=[{"title": "N1", "url": "https://b.com", "description": "D1"}],
        )
        result = await skill.execute({"query": "AI market"}, _ctx())
        assert result.success
        assert result.data["source_count"] == 2
        assert result.data["web_count"] == 1
        assert result.data["news_count"] == 1

    async def test_empty_query_fails(self):
        skill = _make_skill()
        result = await skill.execute({"query": ""}, _ctx())
        assert not result.success
        assert "No query" in result.error

    async def test_deduplicates_urls(self):
        skill = _make_skill(
            tavily_results=[
                {"title": "T1", "url": "https://a.com", "content": "C1"},
            ],
            news_results=[
                {"title": "T1 dup", "url": "https://a.com", "description": "D1"},
            ],
        )
        result = await skill.execute({"query": "test"}, _ctx())
        assert result.data["source_count"] == 1

    async def test_geography_augments_query(self):
        skill = _make_skill(tavily_results=[])
        await skill.execute({"query": "pizza market", "geography": "New York"}, _ctx())
        call_args = skill.tavily_client.search.call_args
        assert "New York" in call_args[0][0]

    async def test_no_news_when_disabled(self):
        skill = _make_skill(tavily_results=[], news_results=[])
        result = await skill.execute({"query": "test", "include_news": False}, _ctx())
        assert result.success
        skill.gnews_client.search_news.assert_not_awaited()

    async def test_handles_tavily_failure(self):
        skill = _make_skill()
        skill.tavily_client.search = AsyncMock(side_effect=Exception("fail"))
        result = await skill.execute({"query": "test"}, _ctx())
        assert not result.success
        assert "fail" in result.error

    async def test_meta_correct(self):
        skill = _make_skill()
        assert skill.meta.skill_id == "SKL-MRA-01"
        assert skill.meta.name == "web_market_search"
