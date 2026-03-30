"""Tests for TrademarkSearcher (SKL-NTA-08)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.logic.trademark_searcher import TrademarkSearcher


@pytest.fixture
def searcher():
    return TrademarkSearcher()


class TestTrademarkSearcher:
    """Test Tavily-based trademark conflict search."""

    @patch("app.logic.trademark_searcher.settings")
    async def test_no_api_key_returns_unavailable(self, mock_settings, searcher):
        mock_settings.TAVILY_API_KEY = ""
        result = await searcher.search("TestBrand")
        assert result["clear"] is None
        assert "unavailable" in result["notes"]

    @patch("app.logic.trademark_searcher.settings")
    @patch("app.logic.trademark_searcher.httpx.AsyncClient")
    async def test_no_conflicts_returns_clear(
        self, MockClient, mock_settings, searcher
    ):
        mock_settings.TAVILY_API_KEY = "test-key"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "Test unrelated page",
                    "url": "https://example.com",
                    "content": "Nothing relevant here",
                },
            ]
        }

        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await searcher.search("UniqueTestBrand")
        assert result["clear"] is True
        assert result["conflicts"] == []

    @patch("app.logic.trademark_searcher.settings")
    @patch("app.logic.trademark_searcher.httpx.AsyncClient")
    async def test_conflicts_detected(
        self, MockClient, mock_settings, searcher
    ):
        mock_settings.TAVILY_API_KEY = "test-key"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "TestBrand® Registered Trademark",
                    "url": "https://trademark.example.com",
                    "content": "TestBrand is a registered trademark of XYZ Corp.",
                },
                {
                    "title": "TestBrand Wikipedia",
                    "url": "https://en.wikipedia.org",
                    "content": "TestBrand is a popular consumer electronics company.",
                },
            ]
        }

        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await searcher.search("TestBrand")
        assert result["clear"] is False
        assert len(result["conflicts"]) == 1
        assert "registered" in result["conflicts"][0]["snippet"].lower()

    @patch("app.logic.trademark_searcher.settings")
    @patch("app.logic.trademark_searcher.httpx.AsyncClient")
    async def test_api_error_returns_none_clear(
        self, MockClient, mock_settings, searcher
    ):
        mock_settings.TAVILY_API_KEY = "test-key"

        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await searcher.search("TestBrand")
        assert result["clear"] is None
        assert "failed" in result["notes"].lower()

    @patch("app.logic.trademark_searcher.settings")
    @patch("app.logic.trademark_searcher.httpx.AsyncClient")
    async def test_network_exception_returns_error(
        self, MockClient, mock_settings, searcher
    ):
        mock_settings.TAVILY_API_KEY = "test-key"

        mock_instance = AsyncMock()
        mock_instance.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await searcher.search("TestBrand")
        assert result["clear"] is None
        assert "error" in result["notes"].lower()
