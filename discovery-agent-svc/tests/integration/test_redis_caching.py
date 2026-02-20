"""Integration test: Redis caching with real Redis.

Verifies search cache, page cache, and TTL behavior.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
import redis.asyncio as aioredis

from app.cache.redis_manager import PAGE_CACHE_TTL, SEARCH_CACHE_TTL, RedisManager
from app.scrapers.search_engine import SearchEngine

pytestmark = pytest.mark.integration


class TestSearchCache:
    """Search query caching with real Redis."""

    async def test_first_call_caches_results(
        self,
        search_engine_with_mock: SearchEngine,
        redis_client: aioredis.Redis,
    ) -> None:
        results = await search_engine_with_mock.search("brand analysis")
        assert len(results) > 0

        # Verify something was cached in Redis
        keys = await redis_client.keys("discovery:cache:*")
        assert len(keys) == 1

    async def test_second_call_returns_from_cache(
        self,
        search_engine_with_mock: SearchEngine,
    ) -> None:
        # First call — hits the stub
        results1 = await search_engine_with_mock.search("brand analysis")
        call_count_after_first = search_engine_with_mock._search_stub.call_count

        # Second call — should come from cache
        results2 = await search_engine_with_mock.search("brand analysis")
        call_count_after_second = search_engine_with_mock._search_stub.call_count

        # Stub should not have been called a second time
        assert call_count_after_second == call_count_after_first

    async def test_cache_key_has_correct_ttl(
        self,
        search_engine_with_mock: SearchEngine,
        redis_client: aioredis.Redis,
    ) -> None:
        await search_engine_with_mock.search("ttl test query")

        keys = await redis_client.keys("discovery:cache:*")
        assert len(keys) == 1

        ttl = await redis_client.ttl(keys[0])
        # TTL should be close to SEARCH_CACHE_TTL (4 hours = 14400s)
        assert SEARCH_CACHE_TTL - 10 <= ttl <= SEARCH_CACHE_TTL


class TestPageCache:
    """Page content caching with real Redis."""

    async def test_page_cache_stores_and_retrieves(
        self,
        redis_manager: RedisManager,
    ) -> None:
        url = "https://example.com/test-page"
        markdown = "# Test Page\n\nSome content here."

        await redis_manager.set_cached_page(url, markdown)
        cached = await redis_manager.get_cached_page(url)

        assert cached == markdown

    async def test_page_cache_miss_returns_none(
        self,
        redis_manager: RedisManager,
    ) -> None:
        cached = await redis_manager.get_cached_page("https://example.com/nonexistent")
        assert cached is None

    async def test_page_cache_has_correct_ttl(
        self,
        redis_manager: RedisManager,
        redis_client: aioredis.Redis,
    ) -> None:
        url = "https://example.com/ttl-test"
        await redis_manager.set_cached_page(url, "# Content")

        keys = await redis_client.keys("discovery:page:*")
        assert len(keys) == 1

        ttl = await redis_client.ttl(keys[0])
        assert PAGE_CACHE_TTL - 10 <= ttl <= PAGE_CACHE_TTL

    async def test_scrape_uses_page_cache_on_second_call(
        self,
        redis_manager: RedisManager,
        browser_engine_with_mock,
    ) -> None:
        url = "https://example.com/market-analysis"

        # First scrape — gets mock HTML
        result1 = await browser_engine_with_mock.scrape(url, "tenant-1")
        assert result1.html != ""

        # Cache the cleaned content manually (simulating what executor does)
        await redis_manager.set_cached_page(url, "# Cached Markdown")

        # Second scrape — should return cached Markdown
        result2 = await browser_engine_with_mock.scrape(url, "tenant-1")
        assert result2.html == "# Cached Markdown"
        assert result2.content_type == "text/markdown"
