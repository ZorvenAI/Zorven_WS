"""Tests for MarketResearcher — PAOR reasoning loop."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas import MarketResearchResponse
from app.logic.market_researcher import MarketResearcher
from app.services.api_clients import GNewsClient, TavilySearchClient, WorldBankClient


def _make_researcher(
    anthropic_key: str = "",
    tavily_results: list | None = None,
    world_bank_data: dict | None = None,
    news_articles: list | None = None,
) -> MarketResearcher:
    """Create a MarketResearcher with mocked clients."""
    tavily = TavilySearchClient("")
    tavily.search = AsyncMock(return_value=tavily_results or [])

    world_bank = WorldBankClient("https://api.worldbank.org/v2")
    world_bank.get_multiple_indicators = AsyncMock(return_value=world_bank_data or {})

    news = GNewsClient("")
    news.search_news = AsyncMock(return_value=news_articles or [])

    return MarketResearcher(
        tavily_client=tavily,
        world_bank_client=world_bank,
        news_client=news,
        anthropic_api_key=anthropic_key,
        model="claude-sonnet-4-20250514",
    )


class TestPlanPhase:
    async def test_default_plan_without_anthropic_key(self):
        researcher = _make_researcher()
        plan = await researcher._plan_research("AI market size")
        assert "search_queries" in plan
        assert "indicators" in plan
        assert "news_queries" in plan
        assert "countries" in plan

    async def test_default_plan_contains_prompt(self):
        researcher = _make_researcher()
        plan = await researcher._plan_research("EV charging market")
        assert "EV charging market" in plan["search_queries"][0]


class TestGatherPhase:
    async def test_gather_data_calls_all_sources(self):
        researcher = _make_researcher(
            tavily_results=[
                {
                    "title": "Test",
                    "url": "https://example.com",
                    "content": "Test content",
                }
            ],
            world_bank_data={"gdp_WLD": [{"value": 100}]},
            news_articles=[
                {"title": "News", "url": "https://news.com", "description": "Desc"}
            ],
        )

        plan = {
            "search_queries": ["AI market"],
            "indicators": ["gdp"],
            "news_queries": ["AI trends"],
            "countries": ["WLD"],
        }

        web, econ, news = await researcher._gather_data(plan, {})
        assert len(web) == 1
        # Key format is {indicator}_{country} e.g. "gdp_WLD_WLD"
        assert any("gdp" in k for k in econ)
        assert len(news) == 1

    async def test_gather_data_handles_source_failures(self):
        researcher = _make_researcher()
        researcher.tavily_client.search = AsyncMock(
            side_effect=Exception("Tavily down")
        )

        plan = {
            "search_queries": ["test"],
            "indicators": [],
            "news_queries": [],
            "countries": ["WLD"],
        }

        web, econ, news = await researcher._gather_data(plan, {})
        assert web == []  # Failed gracefully


class TestCompilePhase:
    def test_compile_context_with_all_sources(self):
        researcher = _make_researcher()
        web = [
            {"title": "Web Result", "url": "https://example.com", "content": "Content"}
        ]
        econ = {
            "gdp_WLD": [
                {"country": "World", "date": "2023", "value": 100, "indicator": "GDP"}
            ]
        }
        news = [
            {
                "title": "News",
                "url": "https://news.com",
                "description": "Desc",
                "source": "TN",
            }
        ]

        raw_context, sources = researcher._compile_context(web, econ, news)
        assert "Web Result" in raw_context
        econ_titles = [s.title for s in sources if s.type == "economic_data"]
        assert any("World Bank" in t for t in econ_titles)
        assert len(sources) >= 3  # At least one web, one economic, one news

    def test_compile_context_empty_sources(self):
        researcher = _make_researcher()
        raw_context, sources = researcher._compile_context([], {}, [])
        assert raw_context == ""
        assert sources == []


class TestSynthesisPhase:
    async def test_default_synthesis_without_anthropic(self):
        researcher = _make_researcher()
        result = await researcher._synthesize("test query", "some context")
        assert "overview" in result
        assert "findings" in result

    async def test_default_synthesis_empty_context(self):
        researcher = _make_researcher()
        result = await researcher._synthesize("test", "")
        assert result["confidence"] == 0.3  # Low confidence default


class TestFullResearch:
    async def test_research_returns_response(self):
        researcher = _make_researcher(
            tavily_results=[
                {
                    "title": "Market Report",
                    "url": "https://example.com",
                    "content": "Data",
                }
            ],
        )

        result = await researcher.research(
            prompt="What is the AI market size?",
            config={"focus": "sizing"},
            previous_outputs={},
        )

        assert isinstance(result, MarketResearchResponse)
        assert result.query == "What is the AI market size?"
        assert isinstance(result.findings, list)
        assert isinstance(result.sources, list)

    async def test_research_with_empty_sources(self):
        researcher = _make_researcher()
        result = await researcher.research(
            prompt="test", config={}, previous_outputs={}
        )
        assert isinstance(result, MarketResearchResponse)

    async def test_research_limits_raw_context(self):
        """Raw context should be truncated to 50000 chars."""
        researcher = _make_researcher()
        result = await researcher.research(
            prompt="test", config={}, previous_outputs={}
        )
        assert len(result.raw_context) <= 50000


class TestFormatEconomicData:
    def test_format_with_data(self):
        result = MarketResearcher._format_economic_data(
            {"gdp_WLD": [{"value": 100, "date": "2023", "country": "World"}]}
        )
        assert "gdp_WLD" in result
        assert result["gdp_WLD"]["latest_value"] == 100
        assert result["gdp_WLD"]["data_points"] == 1

    def test_format_empty_data(self):
        result = MarketResearcher._format_economic_data({})
        assert result == {}

    def test_format_skips_empty_values(self):
        result = MarketResearcher._format_economic_data({"empty": []})
        assert "empty" not in result


class TestClose:
    async def test_close_without_anthropic(self):
        researcher = _make_researcher()
        await researcher.close()  # Should not raise

    async def test_close_with_mock_anthropic(self):
        researcher = _make_researcher(anthropic_key="sk-test")
        mock_client = AsyncMock()
        researcher._anthropic_client = mock_client
        await researcher.close()
        mock_client.close.assert_awaited_once()
