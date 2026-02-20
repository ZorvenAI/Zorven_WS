"""Shared integration test fixtures.

Requires Redis running on localhost:6379 (or DISCOVERY_TEST_REDIS_URL).
All tests marked with @pytest.mark.integration.
"""

import os
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.main import app
from app.scrapers.browser_engine import BrowserEngine, ScrapeResult
from app.scrapers.data_cleaner import DataCleaner
from app.scrapers.search_engine import SearchEngine
from app.services.discovery_executor import DiscoveryExecutor

REDIS_URL = os.environ.get("DISCOVERY_TEST_REDIS_URL", "redis://localhost:6379/2")


@pytest.fixture
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Real Redis connection. Flushes DB before each test."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.flushdb()
        yield r
    finally:
        await r.flushdb()
        await r.aclose()


@pytest.fixture
async def redis_manager(redis_client: aioredis.Redis) -> AsyncGenerator[RedisManager, None]:
    """RedisManager wired to real Redis."""
    manager = RedisManager(REDIS_URL)
    manager._redis = redis_client
    yield manager
    # Don't close — redis_client fixture handles that


@pytest.fixture
def mock_search_results() -> list[dict[str, str]]:
    """Controlled search results for integration tests."""
    return [
        {
            "title": "Market Analysis Report",
            "url": "https://example.com/market-analysis",
            "snippet": "Key market trends show growth in brand equity.",
        },
        {
            "title": "Competitor Overview",
            "url": "https://example.com/competitors",
            "snippet": "Top competitors include Alpha Corp and Beta Inc.",
        },
        {
            "title": "Brand Rankings 2024",
            "url": "https://example.com/brand-rankings",
            "snippet": "Annual brand value rankings across industries.",
        },
    ]


@pytest.fixture
def mock_html_pages() -> dict[str, str]:
    """Controlled HTML content for scrape mocking."""
    return {
        "https://example.com/market-analysis": (
            "<html><head><title>Market</title></head>"
            "<body><h1>Market Analysis</h1>"
            "<p>The brand equity market shows strong growth.</p>"
            "<script>analytics();</script></body></html>"
        ),
        "https://example.com/competitors": (
            "<html><body><h1>Competitors</h1>"
            "<p>Alpha Corp leads with 30% market share.</p>"
            "<nav>Menu</nav></body></html>"
        ),
        "https://example.com/brand-rankings": (
            "<html><body><h1>Rankings</h1>"
            "<p>Top 10 brands by value in 2024.</p>"
            "</body></html>"
        ),
    }


@pytest.fixture
def search_engine_with_mock(
    redis_manager: RedisManager,
    mock_search_results: list[dict[str, str]],
) -> SearchEngine:
    """SearchEngine backed by real Redis, Tavily mocked."""
    engine = SearchEngine(tavily_api_key="", redis_manager=redis_manager)
    # Override stub to return controlled results
    engine._search_stub = MagicMock(return_value=mock_search_results)
    return engine


@pytest.fixture
def browser_engine_with_mock(
    redis_manager: RedisManager,
    mock_html_pages: dict[str, str],
) -> BrowserEngine:
    """BrowserEngine backed by real Redis, HTTP mocked."""
    engine = BrowserEngine(timeout=10, redis_manager=redis_manager)

    original_scrape = engine.scrape

    async def mock_scrape(url: str, tenant_id: str = "") -> ScrapeResult:
        # Check real Redis cache first
        if engine.redis_manager:
            cached = await engine.redis_manager.get_cached_page(url)
            if cached is not None:
                return ScrapeResult(html=cached, content_type="text/markdown", status_code=200)

        # Return mock HTML instead of making real HTTP request
        html = mock_html_pages.get(url, "")
        return ScrapeResult(html=html, content_type="text/html", status_code=200 if html else 404)

    engine.scrape = mock_scrape
    return engine


@pytest.fixture
def kafka_capture() -> list[dict[str, Any]]:
    """Captures Kafka events in a list instead of sending to broker."""
    return []


@pytest.fixture
async def executor_with_redis(
    search_engine_with_mock: SearchEngine,
    browser_engine_with_mock: BrowserEngine,
    redis_manager: RedisManager,
) -> AsyncGenerator[DiscoveryExecutor, None]:
    """DiscoveryExecutor wired to real Redis with mocked external APIs."""
    executor = DiscoveryExecutor(
        search_engine=search_engine_with_mock,
        browser_engine=browser_engine_with_mock,
        data_cleaner=DataCleaner(),
        redis_manager=redis_manager,
    )
    yield executor


@pytest.fixture
async def app_with_redis(
    executor_with_redis: DiscoveryExecutor,
) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI TestClient with real Redis wired into the app."""
    # Inject the executor into routes
    old_executor = routes.executor
    routes.executor = executor_with_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    routes.executor = old_executor


@pytest.fixture
def valid_execute_payload() -> dict[str, Any]:
    """Payload matching ExternalWrapper contract."""
    return {
        "input_prompt": "Analyze brand positioning for Acme Corp",
        "input_context": {"company_id": 42},
        "tenant_context": {
            "tenant_id": "1",
            "gcs_raw_bucket": "brand-automator/1/",
            "gcs_processed_bucket": "brand-automator-curated/1/",
            "rag_data_store_id": "ds-123",
        },
        "config": {"focus": "market_trends,competitors"},
        "previous_outputs": {},
    }


@pytest.fixture
def tenant_headers() -> dict[str, str]:
    """Headers with X-Tenant-ID."""
    return {"X-Tenant-ID": "test-tenant"}
