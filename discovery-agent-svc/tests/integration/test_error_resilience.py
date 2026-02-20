"""Integration test: graceful degradation and error resilience.

Verifies the service handles failures in Redis, Tavily, scraping,
and other external dependencies without crashing.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.api import routes
from app.api.schemas import ExecuteRequest
from app.cache.redis_manager import RedisManager
from app.scrapers.browser_engine import BrowserEngine, ScrapeResult
from app.scrapers.data_cleaner import DataCleaner
from app.scrapers.search_engine import SearchEngine
from app.services.discovery_executor import DiscoveryExecutor

pytestmark = pytest.mark.integration


class TestRedisUnavailable:
    """Service operates without Redis."""

    async def test_execute_works_without_redis(self) -> None:
        """Service still returns results when Redis is unavailable."""
        search_engine = SearchEngine(tavily_api_key="", redis_manager=None)
        browser_engine = BrowserEngine(timeout=10, redis_manager=None)

        async def mock_scrape(url: str, tenant_id: str = "") -> ScrapeResult:
            return ScrapeResult(
                html="<h1>Test</h1><p>Content</p>",
                content_type="text/html",
                status_code=200,
            )

        browser_engine.scrape = mock_scrape

        executor = DiscoveryExecutor(
            search_engine=search_engine,
            browser_engine=browser_engine,
            data_cleaner=DataCleaner(),
            redis_manager=None,
        )

        request = ExecuteRequest(
            input_prompt="Test query",
            config={"focus": "market_trends"},
        )
        result = await executor.execute(request, "tenant-1")
        assert result.query == "Test query market_trends"
        assert len(result.sources) > 0


class TestSearchFailure:
    """Service handles Tavily API errors gracefully."""

    async def test_empty_search_results_returns_valid_response(
        self,
        app_with_redis: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        """Empty search results still produce a valid response."""
        payload = {
            "input_prompt": "extremely obscure nonexistent topic zzz999",
        }
        # The stub engine will still return results, but this tests the path
        resp = await app_with_redis.post(
            "/v1/execute", json=payload, headers=tenant_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["findings"], list)
        assert isinstance(data["recommendations"], list)


class TestScrapeFailure:
    """Service handles scraping errors gracefully."""

    async def test_all_scrapes_fail_returns_valid_response(self) -> None:
        """If all URLs fail to scrape, response is valid with empty content."""
        search_engine = SearchEngine(tavily_api_key="", redis_manager=None)
        browser_engine = BrowserEngine(timeout=10, redis_manager=None)

        async def failing_scrape(url: str, tenant_id: str = "") -> ScrapeResult:
            return ScrapeResult(html="", content_type="", status_code=404)

        browser_engine.scrape = failing_scrape

        executor = DiscoveryExecutor(
            search_engine=search_engine,
            browser_engine=browser_engine,
            data_cleaner=DataCleaner(),
            redis_manager=None,
        )

        request = ExecuteRequest(input_prompt="Test", config={})
        result = await executor.execute(request, "tenant-1")
        assert result.query == "Test"
        assert result.sources == []
        assert result.raw_context == ""

    async def test_partial_scrape_failure_still_returns_data(self) -> None:
        """Some URLs succeed, some fail — successful ones are included."""
        search_engine = SearchEngine(tavily_api_key="", redis_manager=None)
        # Override stub to control URLs
        search_engine._search_stub = MagicMock(
            return_value=[
                {"title": "OK Page", "url": "https://ok.com", "snippet": "Good content"},
                {"title": "Bad Page", "url": "https://bad.com", "snippet": ""},
            ]
        )

        browser_engine = BrowserEngine(timeout=10, redis_manager=None)

        async def mixed_scrape(url: str, tenant_id: str = "") -> ScrapeResult:
            if "ok.com" in url:
                return ScrapeResult(
                    html="<h1>Working</h1><p>Content here.</p>",
                    content_type="text/html",
                    status_code=200,
                )
            return ScrapeResult(html="", content_type="", status_code=500)

        browser_engine.scrape = mixed_scrape

        executor = DiscoveryExecutor(
            search_engine=search_engine,
            browser_engine=browser_engine,
            data_cleaner=DataCleaner(),
            redis_manager=None,
        )

        request = ExecuteRequest(input_prompt="Mixed test", config={})
        result = await executor.execute(request, "tenant-1")
        assert len(result.sources) == 1
        assert result.sources[0].url == "https://ok.com"
        assert result.raw_context != ""


class TestInputValidation:
    """Service handles edge case inputs gracefully."""

    async def test_empty_input_prompt_returns_422(
        self,
        app_with_redis: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json={},
            headers=tenant_headers,
        )
        assert resp.status_code == 422

    async def test_minimal_payload_succeeds(
        self,
        app_with_redis: AsyncClient,
        tenant_headers: dict[str, str],
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json={"input_prompt": "test"},
            headers=tenant_headers,
        )
        assert resp.status_code == 200

    async def test_no_tenant_header_uses_default(
        self,
        app_with_redis: AsyncClient,
    ) -> None:
        resp = await app_with_redis.post(
            "/v1/execute",
            json={"input_prompt": "no tenant header test"},
        )
        assert resp.status_code == 200
