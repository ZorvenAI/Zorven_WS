"""External API clients for the Audience Persona Agent.

- TavilySearchClient: Web search via Tavily API (MCP primary, SDK fallback)
- WebScraperClient: HTTP scraping via httpx + BeautifulSoup
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    sse_client = None  # type: ignore[assignment]


class TavilySearchClient:
    """Web search via Tavily API with MCP primary, SDK fallback."""

    def __init__(self, mcp_server_url: str = "") -> None:
        self._client: Any = None
        self._mcp_server_url = mcp_server_url

    def _ensure_client(self) -> Any:
        """Lazy-initialize the Tavily client."""
        if self._client is None and settings.TAVILY_API_KEY:
            try:
                from tavily import TavilyClient

                self._client = TavilyClient(api_key=settings.TAVILY_API_KEY)
            except Exception as exc:
                logger.warning("Failed to initialize Tavily client: %s", exc)
        return self._client

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
    ) -> list[dict[str, Any]]:
        """Search via MCP (primary) or Tavily SDK (fallback)."""
        # 1. Try MCP if configured
        if self._mcp_server_url and sse_client is not None:
            try:
                results = await self._mcp_search(query, max_results, search_depth)
                if results:
                    logger.info("MCP search succeeded for: %s", query[:80])
                    return results
            except Exception as exc:
                logger.warning("MCP search failed, falling back to SDK: %s", exc)

        # 2. Fallback to SDK
        return await self._sdk_search(query, max_results, search_depth)

    async def _mcp_search(
        self,
        query: str,
        max_results: int,
        search_depth: str,
    ) -> list[dict[str, Any]]:
        """Search via Tavily MCP Server (SSE transport)."""
        arguments: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
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

                text = next((b.text for b in result.content if b.type == "text"), None)
                if text is None:
                    raise RuntimeError("MCP tool returned no text content block")
                raw = json.loads(text)
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", ""),
                    }
                    for r in raw.get("results", raw if isinstance(raw, list) else [])
                ]

    async def _sdk_search(
        self,
        query: str,
        max_results: int,
        search_depth: str,
    ) -> list[dict[str, Any]]:
        """Search via Tavily Python SDK."""
        client = self._ensure_client()
        if not client:
            logger.warning("Tavily client not available, returning empty results")
            return []

        try:
            response = await asyncio.to_thread(
                client.search,
                query=query,
                max_results=max_results,
                search_depth=search_depth,
            )
            results = response.get("results", [])
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in results
            ]
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return []


class WebScraperClient:
    """HTTP scraping via httpx + BeautifulSoup."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AudiencePersonaAgent/1.0; "
                    "+https://prevision.ai)"
                )
            },
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def scrape_page(self, url: str) -> str:
        """Scrape a web page and return cleaned text."""
        if not self._client:
            return ""
        try:
            response = await self._client.get(url)
            response.raise_for_status()

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Cap at 10k chars
            return text[:10000]
        except Exception as exc:
            logger.warning("Failed to scrape %s: %s", url, exc)
            return ""

    async def scrape_multiple(
        self,
        urls: list[str],
        max_pages_per_domain: int = 5,
    ) -> dict[str, str]:
        """Scrape multiple URLs, respecting per-domain limits."""
        domain_counts: dict[str, int] = {}
        results: dict[str, str] = {}

        for url in urls:
            try:
                from urllib.parse import urlparse

                domain = urlparse(url).netloc
            except Exception:
                continue

            if domain_counts.get(domain, 0) >= max_pages_per_domain:
                continue

            text = await self.scrape_page(url)
            if text:
                results[url] = text
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

        return results
