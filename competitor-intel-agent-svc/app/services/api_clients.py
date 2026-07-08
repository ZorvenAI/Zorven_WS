"""
External API clients for competitive intelligence data sources.

Two clients:
  - TavilySearchClient: Web search via Tavily SDK (MCP primary, SDK fallback)
  - WebScraperClient: Website scraping via httpx + BeautifulSoup
"""

import json
import logging
from typing import Any, Optional

import httpx

from app.cache.redis_manager import RedisManager

logger = logging.getLogger(__name__)

try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
except ImportError:
    ClientSession = None  # type: ignore[assignment,misc]
    sse_client = None  # type: ignore[assignment]


class TavilySearchClient:
    """Web search via Tavily API with MCP primary, SDK fallback."""

    def __init__(
        self,
        api_key: str,
        redis_manager: Optional[RedisManager] = None,
        mcp_server_url: str = "",
    ) -> None:
        self.api_key = api_key
        self.redis_manager = redis_manager
        self._client: Any = None
        self._mcp_server_url = mcp_server_url

    def _get_client(self) -> Any:
        """Lazy-init Tavily client."""
        if self._client is None and self.api_key:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search via MCP (primary) or Tavily SDK (fallback).

        Returns list of {title, url, content} dicts.
        Falls back to empty list on failure.
        """
        # 1. Try MCP if configured
        if self._mcp_server_url and sse_client is not None:
            try:
                results = await self._mcp_search(query, max_results)
                if results:
                    logger.info("MCP search succeeded for: %s", query[:80])
                    return results
            except Exception as exc:
                logger.warning("MCP search failed, falling back to SDK: %s", exc)

        # 2. Fallback to SDK
        return await self._sdk_search(query, max_results)

    async def _mcp_search(
        self, query: str, max_results: int
    ) -> list[dict[str, Any]]:
        """Search via Tavily MCP Server (SSE transport)."""
        arguments: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": True,
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

                raw = json.loads(next(b.text for b in result.content if b.type == "text"))
                results = raw.get(
                    "results", raw if isinstance(raw, list) else []
                )
                logger.info(
                    "MCP returned %d results for: %s", len(results), query[:80]
                )
                return results

    async def _sdk_search(
        self, query: str, max_results: int
    ) -> list[dict[str, Any]]:
        """Search via Tavily Python SDK."""
        if not self.api_key:
            logger.info("No Tavily API key - returning empty results")
            return []

        try:
            client = self._get_client()
            if client is None:
                return []

            response = client.search(
                query=query,
                max_results=max_results,
                search_depth="advanced",
                include_answer=True,
            )
            results = response.get("results", [])
            logger.info("Tavily returned %d results for: %s", len(results), query[:80])
            return results
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return []


class WebScraperClient:
    """Website scraping via httpx for competitor profiling.

    Fetches and extracts text content from web pages. Max 5 pages per domain (PG-09).
    Does not check robots.txt or enforce rate limits.
    """

    def __init__(self, max_pages_per_domain: int = 5) -> None:
        self.max_pages_per_domain = max_pages_per_domain

    async def scrape_page(self, url: str, timeout: float = 15.0) -> dict[str, Any]:
        """
        Scrape a single web page and extract text content.

        Returns {url, title, content, status_code} dict. Empty content on failure.
        """
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; BrandAutomatorBot/1.0; "
                        "+https://prevision.ai)"
                    ),
                },
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return {
                        "url": url,
                        "title": "",
                        "content": "",
                        "status_code": resp.status_code,
                    }

                html = resp.text
                title, text = self._extract_text(html)

                return {
                    "url": url,
                    "title": title,
                    "content": text[:10000],
                    "status_code": resp.status_code,
                }
        except Exception as exc:
            logger.warning("Scrape failed for %s: %s", url, exc)
            return {"url": url, "title": "", "content": "", "status_code": 0}

    async def scrape_multiple(
        self, urls: list[str], timeout: float = 15.0
    ) -> list[dict[str, Any]]:
        """Scrape multiple pages, respecting max_pages_per_domain."""
        results = []
        for url in urls[: self.max_pages_per_domain]:
            result = await self.scrape_page(url, timeout)
            results.append(result)
        return results

    @staticmethod
    def _extract_text(html: str) -> tuple[str, str]:
        """Extract title and body text from HTML."""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # Remove script and style elements
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()

            title = ""
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            text = soup.get_text(separator="\n", strip=True)
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = "\n".join(lines)

            return title, text
        except ImportError:
            logger.warning("BeautifulSoup not installed - returning raw HTML")
            return "", html[:5000]
        except Exception as exc:
            logger.warning("HTML extraction failed: %s", exc)
            return "", ""
