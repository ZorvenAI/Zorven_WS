"""Tests for API clients — Tavily, World Bank, GNews."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.api_clients import GNewsClient, TavilySearchClient, WorldBankClient


class TestTavilySearchClient:
    def test_no_api_key_returns_empty(self):
        client = TavilySearchClient("")
        assert client.api_key == ""

    async def test_search_no_api_key(self):
        client = TavilySearchClient("")
        result = await client.search("test query")
        assert result == []

    async def test_search_with_api_key(self):
        client = TavilySearchClient("tvly-test-key")
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {
            "results": [
                {
                    "title": "Result 1",
                    "url": "https://example.com/1",
                    "content": "Content 1",
                },
                {
                    "title": "Result 2",
                    "url": "https://example.com/2",
                    "content": "Content 2",
                },
            ]
        }
        client._client = mock_tavily

        results = await client.search("AI market size", max_results=5)
        assert len(results) == 2
        assert results[0]["title"] == "Result 1"

    async def test_search_exception_returns_empty(self):
        client = TavilySearchClient("tvly-test-key")
        mock_tavily = MagicMock()
        mock_tavily.search.side_effect = Exception("API error")
        client._client = mock_tavily

        results = await client.search("test")
        assert results == []


class TestWorldBankClient:
    def setup_method(self):
        self.client = WorldBankClient("https://api.worldbank.org/v2")

    def test_indicator_codes(self):
        assert "gdp" in WorldBankClient.INDICATORS
        assert "inflation" in WorldBankClient.INDICATORS
        assert "unemployment" in WorldBankClient.INDICATORS
        assert WorldBankClient.INDICATORS["gdp"] == "NY.GDP.MKTP.CD"

    @patch("app.services.api_clients.httpx.AsyncClient")
    async def test_get_indicator_success(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"page": 1, "pages": 1, "total": 2},
            [
                {
                    "country": {"value": "World"},
                    "date": "2023",
                    "value": 100000000,
                    "indicator": {"value": "GDP (current US$)"},
                },
                {
                    "country": {"value": "World"},
                    "date": "2022",
                    "value": 95000000,
                    "indicator": {"value": "GDP (current US$)"},
                },
            ],
        ]
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        results = await self.client.get_indicator("NY.GDP.MKTP.CD")
        assert len(results) == 2
        assert results[0]["country"] == "World"
        assert results[0]["value"] == 100000000

    @patch("app.services.api_clients.httpx.AsyncClient")
    async def test_get_indicator_error_returns_empty(self, mock_client_cls):
        mock_http = AsyncMock()
        mock_http.get.side_effect = httpx.HTTPError("Connection failed")
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        results = await self.client.get_indicator("NY.GDP.MKTP.CD")
        assert results == []

    async def test_get_multiple_indicators(self):
        """Test that get_multiple_indicators calls get_indicator for each name."""
        self.client.get_indicator = AsyncMock(return_value=[{"value": 100}])
        results = await self.client.get_multiple_indicators(["gdp", "inflation"])
        assert "gdp" in results
        assert "inflation" in results
        assert self.client.get_indicator.await_count == 2


class TestGNewsClient:
    async def test_search_no_api_key(self):
        client = GNewsClient("")
        result = await client.search_news("test query")
        assert result == []

    @patch("app.services.api_clients.httpx.AsyncClient")
    async def test_search_news_success(self, mock_client_cls):
        client = GNewsClient("test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "articles": [
                {
                    "title": "AI Market Growing",
                    "description": "The AI market is expanding",
                    "url": "https://news.example.com/1",
                    "publishedAt": "2024-01-15T10:00:00Z",
                    "source": {"name": "TechNews"},
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_response
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        results = await client.search_news("AI market")
        assert len(results) == 1
        assert results[0]["title"] == "AI Market Growing"
        assert results[0]["source"] == "TechNews"

    @patch("app.services.api_clients.httpx.AsyncClient")
    async def test_search_news_error_returns_empty(self, mock_client_cls):
        client = GNewsClient("test-key")

        mock_http = AsyncMock()
        mock_http.get.side_effect = Exception("API error")
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        results = await client.search_news("test")
        assert results == []
