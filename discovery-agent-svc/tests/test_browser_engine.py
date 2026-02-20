"""Tests for BrowserEngine — URL scraping with caching."""

from unittest.mock import AsyncMock

import httpx

from app.scrapers.browser_engine import BrowserEngine


class TestScraping:
    """URL scraping tests."""

    async def test_successful_scrape(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://example.com/page",
            html="<html><body><h1>Hello</h1></body></html>",
        )
        engine = BrowserEngine(timeout=10)
        result = await engine.scrape("https://example.com/page")
        assert result.html == "<html><body><h1>Hello</h1></body></html>"
        assert result.status_code == 200

    async def test_scrape_returns_content_type(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://example.com/doc.pdf",
            content=b"%PDF-1.4",
            headers={"content-type": "application/pdf"},
        )
        engine = BrowserEngine(timeout=10)
        result = await engine.scrape("https://example.com/doc.pdf")
        assert "application/pdf" in result.content_type

    async def test_404_returns_empty(self, httpx_mock) -> None:
        httpx_mock.add_response(
            url="https://example.com/missing",
            status_code=404,
        )
        engine = BrowserEngine(timeout=10)
        result = await engine.scrape("https://example.com/missing")
        assert result.html == ""
        assert result.status_code == 404

    async def test_connection_error_returns_empty(self, httpx_mock) -> None:
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="https://unreachable.com",
        )
        engine = BrowserEngine(timeout=10)
        result = await engine.scrape("https://unreachable.com")
        assert result.html == ""
        assert result.status_code == 0

    async def test_timeout_returns_empty(self, httpx_mock) -> None:
        httpx_mock.add_exception(
            httpx.ReadTimeout("Timeout"),
            url="https://slow.com",
        )
        engine = BrowserEngine(timeout=1)
        result = await engine.scrape("https://slow.com")
        assert result.html == ""
        assert result.status_code == 0


class TestPageCache:
    """Redis page cache integration tests."""

    async def test_cache_hit_returns_cached_content(self) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_page = AsyncMock(return_value="# Cached Content")

        engine = BrowserEngine(timeout=10, redis_manager=mock_redis)
        result = await engine.scrape("https://example.com/cached")
        assert result.html == "# Cached Content"
        assert result.content_type == "text/markdown"

    async def test_cache_miss_fetches_url(self, httpx_mock) -> None:
        mock_redis = AsyncMock()
        mock_redis.get_cached_page = AsyncMock(return_value=None)

        httpx_mock.add_response(
            url="https://example.com/fresh",
            html="<h1>Fresh Content</h1>",
        )

        engine = BrowserEngine(timeout=10, redis_manager=mock_redis)
        result = await engine.scrape("https://example.com/fresh")
        assert "Fresh Content" in result.html
