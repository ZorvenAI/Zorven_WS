"""
Search engine — Tavily API integration with Redis caching.

When DISCOVERY_TAVILY_API_KEY is empty, operates in stub mode
returning realistic mock search results. Supports MCP-first, SDK-fallback.
"""

import json
import logging
from typing import Any, Optional

from app.cache.redis_manager import RedisManager

logger = logging.getLogger(__name__)

try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    sse_client = None  # type: ignore[assignment]


class SearchEngine:
    """Web search via Tavily API with MCP primary, SDK fallback, caching."""

    def __init__(
        self,
        tavily_api_key: str = "",
        redis_manager: Optional[RedisManager] = None,
        mcp_server_url: str = "",
    ) -> None:
        self.api_key = tavily_api_key
        self.redis_manager = redis_manager
        self._tavily_client: Any = None
        self._mcp_server_url = mcp_server_url

        if self.api_key:
            try:
                from tavily import TavilyClient

                self._tavily_client = TavilyClient(api_key=self.api_key)
                logger.info("Tavily search engine initialized (live mode)")
            except Exception as exc:
                logger.warning("Failed to initialize Tavily client: %s", exc)
        else:
            logger.info("Search engine running in stub mode (no API key)")

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        """
        Search the web for the given query.

        Returns a list of {title, url, snippet} dicts.
        Checks Redis cache first, falls back to MCP, SDK, or stub.
        """
        # Check cache
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_search(query)
            if cached is not None:
                return cached.get("results", [])

        # 1. Try MCP if configured
        if self._mcp_server_url and sse_client is not None:
            try:
                results = await self._search_mcp(query, max_results)
                if results:
                    logger.info("MCP search succeeded for: %s", query[:80])
                    if self.redis_manager:
                        await self.redis_manager.set_cached_search(
                            query, {"results": results}
                        )
                    return results
            except Exception as exc:
                logger.warning("MCP search failed, falling back to SDK: %s", exc)

        # 2. Fallback to SDK or stub
        if self._tavily_client:
            results = await self._search_tavily(query, max_results)
        else:
            results = self._search_stub(query, max_results)

        # Cache results
        if self.redis_manager and results:
            await self.redis_manager.set_cached_search(query, {"results": results})

        return results

    async def _search_mcp(
        self, query: str, max_results: int
    ) -> list[dict[str, str]]:
        """Search via Tavily MCP Server (SSE transport)."""
        arguments: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }

        async with sse_client(url=self._mcp_server_url, timeout=15) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                result = await session.call_tool(
                    name="tavily_search", arguments=arguments
                )
                if hasattr(result, "isError") and result.isError:
                    error_text = ""
                    if hasattr(result, "content"):
                        for item in result.content:
                            if hasattr(item, "text"):
                                error_text += item.text
                    raise RuntimeError(f"MCP tool error: {error_text}")

                raw = json.loads(result.content[0].text)
                results = []
                for item in raw.get("results", raw if isinstance(raw, list) else []):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "snippet": item.get("content", "")[:500],
                        }
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
