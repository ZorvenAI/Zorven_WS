"""Tests for DiscoveryExecutor — core orchestration logic."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.schemas import ExecuteRequest
from app.scrapers.browser_engine import ScrapeResult
from app.services.discovery_executor import DiscoveryExecutor


def _make_request(**overrides) -> ExecuteRequest:
    """Create a test ExecuteRequest."""
    defaults = {
        "input_prompt": "Analyze brand positioning for Acme Corp",
        "input_context": {},
        "tenant_context": {"tenant_id": "1"},
        "config": {"focus": "market_trends,competitors"},
        "previous_outputs": {},
    }
    defaults.update(overrides)
    return ExecuteRequest(**defaults)


def _make_executor(
    search_results=None,
    scrape_html="<h1>Title</h1><p>Content</p>",
    rate_allowed=True,
):
    """Create an executor with mocked dependencies."""
    mock_search = AsyncMock()
    mock_search.search = AsyncMock(
        return_value=search_results
        if search_results is not None
        else [
            {"title": "Result 1", "url": "https://example.com/1", "snippet": "Finding about markets"},
            {"title": "Result 2", "url": "https://example.com/2", "snippet": "Competitor data"},
        ]
    )

    mock_browser = AsyncMock()
    mock_browser.scrape = AsyncMock(
        return_value=ScrapeResult(html=scrape_html, content_type="text/html", status_code=200)
    )

    from app.scrapers.data_cleaner import DataCleaner

    data_cleaner = DataCleaner()

    mock_redis = AsyncMock()
    mock_redis.check_rate_limit = AsyncMock(return_value=rate_allowed)
    mock_redis.set_cached_page = AsyncMock()

    executor = DiscoveryExecutor(
        search_engine=mock_search,
        browser_engine=mock_browser,
        data_cleaner=data_cleaner,
        redis_manager=mock_redis,
    )
    return executor, mock_search, mock_browser, mock_redis


class TestQueryBuilding:
    """Query construction from input_prompt + config.focus."""

    async def test_builds_query_from_prompt_and_focus(self) -> None:
        executor, _, _, _ = _make_executor()
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert "Analyze brand positioning for Acme Corp" in response.query
        assert "market_trends" in response.query
        assert "competitors" in response.query

    async def test_builds_query_without_focus(self) -> None:
        executor, _, _, _ = _make_executor()
        request = _make_request(config={})
        response = await executor.execute(request, "tenant-1")
        assert response.query == "Analyze brand positioning for Acme Corp"


class TestRateLimiting:
    """Rate limit enforcement tests."""

    async def test_rate_limit_exceeded_raises_429(self) -> None:
        executor, _, _, _ = _make_executor(rate_allowed=False)
        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await executor.execute(request, "tenant-1")
        assert exc_info.value.status_code == 429

    async def test_rate_limit_checks_correct_tenant(self) -> None:
        executor, _, _, mock_redis = _make_executor()
        request = _make_request()
        await executor.execute(request, "tenant-42")
        mock_redis.check_rate_limit.assert_called_once_with("tenant-42", limit=10)


class TestSearchAndScrape:
    """Search → scrape → clean flow tests."""

    async def test_calls_search_engine(self) -> None:
        executor, mock_search, _, _ = _make_executor()
        request = _make_request()
        await executor.execute(request, "tenant-1")
        mock_search.search.assert_called_once()

    async def test_scrapes_each_url(self) -> None:
        executor, _, mock_browser, _ = _make_executor()
        request = _make_request()
        await executor.execute(request, "tenant-1")
        assert mock_browser.scrape.call_count == 2

    async def test_response_has_correct_shape(self) -> None:
        executor, _, _, _ = _make_executor()
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.query
        assert isinstance(response.sources, list)
        assert isinstance(response.findings, list)
        assert isinstance(response.recommendations, list)
        assert isinstance(response.raw_context, str)

    async def test_sources_match_scraped_urls(self) -> None:
        executor, _, _, _ = _make_executor()
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        urls = [s.url for s in response.sources]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls

    async def test_caches_cleaned_pages(self) -> None:
        executor, _, _, mock_redis = _make_executor()
        request = _make_request()
        await executor.execute(request, "tenant-1")
        assert mock_redis.set_cached_page.call_count == 2

    async def test_skips_downloadable_files(self) -> None:
        executor, _, mock_browser, _ = _make_executor(
            search_results=[
                {"title": "PDF Report", "url": "https://example.com/report.pdf", "snippet": "A PDF"},
            ]
        )
        mock_browser.scrape = AsyncMock(
            return_value=ScrapeResult(html="", content_type="application/pdf", status_code=200)
        )
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert any(s.type == "document" for s in response.sources)


class TestEmptyResults:
    """Edge cases with empty/failed results."""

    async def test_empty_search_results(self) -> None:
        executor, _, _, _ = _make_executor(search_results=[])
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.sources == []
        assert "No results found" in response.recommendations[0]

    async def test_all_scrapes_fail(self) -> None:
        executor, _, mock_browser, _ = _make_executor()
        mock_browser.scrape = AsyncMock(
            return_value=ScrapeResult(html="", content_type="", status_code=0)
        )
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.raw_context == ""

    async def test_no_redis_still_works(self) -> None:
        mock_search = AsyncMock()
        mock_search.search = AsyncMock(
            return_value=[{"title": "R", "url": "https://a.com", "snippet": "S"}]
        )
        mock_browser = AsyncMock()
        mock_browser.scrape = AsyncMock(
            return_value=ScrapeResult(html="<p>Hi</p>", content_type="text/html", status_code=200)
        )
        from app.scrapers.data_cleaner import DataCleaner

        executor = DiscoveryExecutor(
            search_engine=mock_search,
            browser_engine=mock_browser,
            data_cleaner=DataCleaner(),
            redis_manager=None,
        )
        request = _make_request()
        response = await executor.execute(request, "tenant-1")
        assert response.query


class TestCleanup:
    """Resource cleanup tests."""

    async def test_close_closes_redis(self) -> None:
        executor, _, _, mock_redis = _make_executor()
        await executor.close()
        mock_redis.close.assert_called_once()
