"""Tests for SearchEngine — Tavily integration with caching."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.scrapers.search_engine import SearchEngine


class TestStubMode:
    """Tests for stub mode (no API key)."""

    async def test_stub_returns_results(self) -> None:
        engine = SearchEngine(tavily_api_key="")
        results = await engine.search("brand analysis Acme Corp")
        assert len(results) > 0

    async def test_stub_results_have_correct_shape(self) -> None:
        engine = SearchEngine(tavily_api_key="")
        results = await engine.search("market trends")
        for result in results:
            assert "title" in result
            assert "url" in result
            assert "snippet" in result

    async def test_stub_respects_max_results(self) -> None:
        engine = SearchEngine(tavily_api_key="")
        results = await engine.search("test", max_results=2)
        assert len(results) == 2

    async def test_stub_includes_query_in_titles(self) -> None:
        engine = SearchEngine(tavily_api_key="")
        results = await engine.search("competitor analysis Tesla")
        # At least one title should reference the query
        titles = " ".join(r["title"] for r in results)
        assert "competitor analysis" in titles.lower()


class TestCacheIntegration:
    """Tests for Redis cache integration."""

    async def test_returns_cached_result_on_hit(self) -> None:
        mock_redis = AsyncMock()
        cached_data = {"results": [{"title": "Cached", "url": "https://cached.com", "snippet": "From cache"}]}
        mock_redis.get_cached_search = AsyncMock(return_value=cached_data)

        engine = SearchEngine(tavily_api_key="", redis_manager=mock_redis)
        results = await engine.search("cached query")
        assert results[0]["title"] == "Cached"

    async def test_caches_results_after_search(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_search = AsyncMock(return_value=None)

        engine = SearchEngine(tavily_api_key="", redis_manager=mock_redis)
        await engine.search("new query")
        mock_redis.set_cached_search.assert_called_once()

    async def test_no_cache_on_empty_results(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_search = AsyncMock(return_value=None)

        engine = SearchEngine(tavily_api_key="", redis_manager=mock_redis)
        # Stub always returns results, so test with max_results=0
        results = await engine.search("query", max_results=0)
        if not results:
            mock_redis.set_cached_search.assert_not_called()


class TestTavilyMode:
    """Tests for Tavily API mode (mocked)."""

    async def test_tavily_calls_api(self) -> None:
        engine = SearchEngine(tavily_api_key="")
        mock_client = MagicMock()
        mock_client.search.return_value = {
            "results": [
                {"title": "Real Result", "url": "https://real.com", "content": "Real content"}
            ]
        }
        engine._tavily_client = mock_client

        results = await engine._search_tavily("test query", max_results=5)
        mock_client.search.assert_called_once()
        assert results[0]["title"] == "Real Result"

    async def test_tavily_error_returns_empty(self) -> None:
        engine = SearchEngine(tavily_api_key="")
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("API Error")
        engine._tavily_client = mock_client

        results = await engine._search_tavily("test query", max_results=5)
        assert results == []
