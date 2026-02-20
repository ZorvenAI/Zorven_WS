"""
Search engine — Tavily API integration with Redis caching.

When DISCOVERY_TAVILY_API_KEY is empty, operates in stub mode
returning realistic mock search results.
"""

import logging
from typing import Any, Optional

from app.cache.redis_manager import RedisManager

logger = logging.getLogger(__name__)


class SearchEngine:
    """Web search via Tavily API with caching and stub fallback."""

    def __init__(
        self,
        tavily_api_key: str = "",
        redis_manager: Optional[RedisManager] = None,
    ) -> None:
        self.api_key = tavily_api_key
        self.redis_manager = redis_manager
        self._tavily_client: Any = None

        if self.api_key:
            try:
                from tavily import TavilyClient

                self._tavily_client = TavilyClient(api_key=self.api_key)
                logger.info("Tavily search engine initialized (live mode)")
            except Exception as exc:
                logger.warning("Failed to initialize Tavily client: %s", exc)
        else:
            logger.info("Search engine running in stub mode (no API key)")

    async def search(
        self, query: str, max_results: int = 5
    ) -> list[dict[str, str]]:
        """
        Search the web for the given query.

        Returns a list of {title, url, snippet} dicts.
        Checks Redis cache first, falls back to API or stub.
        """
        # Check cache
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_search(query)
            if cached is not None:
                return cached.get("results", [])

        # Execute search
        if self._tavily_client:
            results = await self._search_tavily(query, max_results)
        else:
            results = self._search_stub(query, max_results)

        # Cache results
        if self.redis_manager and results:
            await self.redis_manager.set_cached_search(
                query, {"results": results}
            )

        return results

    async def _search_tavily(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        """Search using the Tavily API."""
        try:
            response = self._tavily_client.search(
                query=query,
                max_results=max_results,
                search_depth="basic",
            )
            results = []
            for item in response.get("results", []):
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", "")[:500],
                    }
                )
            return results
        except Exception as exc:
            logger.error("Tavily search failed: %s", exc)
            return []

    @staticmethod
    def _search_stub(query: str, max_results: int) -> list[dict[str, str]]:
        """Return realistic mock search results based on query keywords."""
        keywords = query.lower().split()

        stub_sources = [
            {
                "title": f"Market Analysis: {query[:60]}",
                "url": "https://example.com/market-analysis",
                "snippet": (
                    "Comprehensive market analysis covering industry trends, "
                    "competitive landscape, and growth projections."
                ),
            },
            {
                "title": f"Industry Report: {query[:60]}",
                "url": "https://example.com/industry-report",
                "snippet": (
                    "Detailed industry report with financial benchmarks, "
                    "market sizing, and strategic recommendations."
                ),
            },
            {
                "title": f"Competitive Intelligence: {query[:40]}",
                "url": "https://example.com/competitive-intel",
                "snippet": (
                    "Competitive intelligence briefing including "
                    "SWOT analysis and market positioning data."
                ),
            },
            {
                "title": f"Brand Insights: {query[:50]}",
                "url": "https://example.com/brand-insights",
                "snippet": (
                    "Brand perception study with consumer sentiment "
                    "analysis and awareness metrics."
                ),
            },
            {
                "title": f"Financial Overview: {query[:45]}",
                "url": "https://example.com/financial-overview",
                "snippet": (
                    "Financial overview including revenue trends, "
                    "valuation metrics, and royalty rate benchmarks."
                ),
            },
        ]

        return stub_sources[:max_results]
