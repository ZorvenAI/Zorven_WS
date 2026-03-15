"""API clients for external data sources.

TavilySearchClient: MCP-first, SDK fallback
WebScraperClient: httpx + BeautifulSoup
"""

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class TavilySearchClient:
    """Tavily search client with MCP-first, SDK fallback."""

    def __init__(self, mcp_server_url: str = "") -> None:
        self._mcp_url = mcp_server_url
        self._sdk_client = None
        self._http_client: httpx.AsyncClient | None = None

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_domains: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search via MCP server or SDK fallback."""
        # Try MCP first
        if self._mcp_url:
            try:
                return await self._search_mcp(
                    query, max_results, search_depth, include_domains
                )
            except Exception as exc:
                logger.warning("MCP search failed, falling back to SDK: %s", exc)

        # SDK fallback
        try:
            return await self._search_sdk(
                query, max_results, search_depth, include_domains
            )
        except Exception as exc:
            logger.warning("Tavily SDK search failed: %s", exc)
            return []

    async def _search_mcp(
        self,
        query: str,
        max_results: int,
        search_depth: str,
        include_domains: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Search via Tavily MCP server."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30.0)

        payload: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        if include_domains:
            payload["include_domains"] = include_domains

        resp = await self._http_client.post(
            f"{self._mcp_url}/search",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            }
            for r in results
        ]

    async def _search_sdk(
        self,
        query: str,
        max_results: int,
        search_depth: str,
        include_domains: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Search via Tavily Python SDK."""
        if not self._sdk_client:
            from app.core.config import settings

            if not settings.TAVILY_API_KEY:
                return []
            from tavily import AsyncTavilyClient

            self._sdk_client = AsyncTavilyClient(
                api_key=settings.TAVILY_API_KEY
            )

        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains

        response = await self._sdk_client.search(**kwargs)
        results = response.get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            }
            for r in results
        ]

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()


class WebScraperClient:
    """HTTP scraper using httpx + BeautifulSoup."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; VoCABot/1.0; "
                    "+https://prevision.ai/bot)"
                )
            },
        )

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    async def scrape(self, url: str, max_chars: int = 5000) -> str:
        """Scrape and clean a URL's text content."""
        if not self._client:
            return ""
        try:
            resp = await self._client.get(url)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Remove script/style
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text[:max_chars]
        except Exception as exc:
            logger.warning("Scrape failed for %s: %s", url, exc)
            return ""
