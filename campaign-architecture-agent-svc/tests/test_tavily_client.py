"""Tests for TavilyClient."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.tavily_client import TavilyClient


class TestTavilyClient:
    """Test the Tavily web research client."""

    async def test_stub_mode_when_no_api_key(self):
        """No API key means stub mode — returns empty dict."""
        client = TavilyClient(api_key="", redis_manager=None)
        assert client.enabled is False
        result = await client.search_benchmarks("SaaS")
        assert result == {}

    async def test_search_benchmarks_returns_results(self):
        """With API key, search_benchmarks calls Tavily and returns data."""
        mock_redis = AsyncMock()
        mock_redis.get_json = AsyncMock(return_value=None)
        mock_redis.set_json = AsyncMock()

        client = TavilyClient(api_key="test-key", redis_manager=mock_redis)

        with patch.object(client, "_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {
                "answer": "CPM $8-12",
                "results": [{"title": "Report", "url": "https://example.com"}],
                "query": "SaaS benchmarks",
            }
            result = await client.search_benchmarks("SaaS")

        assert result["answer"] == "CPM $8-12"
        assert len(result["results"]) == 1

    async def test_search_benchmarks_uses_cache(self):
        """Cached benchmarks are returned without calling Tavily API."""
        cached_data = {"answer": "cached", "results": []}
        mock_redis = AsyncMock()
        mock_redis.get_json = AsyncMock(return_value=cached_data)

        client = TavilyClient(api_key="test-key", redis_manager=mock_redis)

        with patch.object(client, "_search", new_callable=AsyncMock) as mock_search:
            result = await client.search_benchmarks("SaaS")

        mock_search.assert_not_called()
        assert result["answer"] == "cached"

    async def test_search_competitor_ads_returns_results(self):
        """search_competitor_ads calls Tavily with competitor names."""
        mock_redis = AsyncMock()
        mock_redis.get_json = AsyncMock(return_value=None)
        mock_redis.set_json = AsyncMock()

        client = TavilyClient(api_key="test-key", redis_manager=mock_redis)

        with patch.object(client, "_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {
                "answer": "Competitor uses video ads",
                "results": [],
                "query": "competitor ads",
            }
            result = await client.search_competitor_ads(["CompetitorA"], "SaaS")

        assert result["answer"] == "Competitor uses video ads"
        mock_search.assert_awaited_once()
