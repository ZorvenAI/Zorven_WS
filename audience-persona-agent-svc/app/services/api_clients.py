"""External API clients for the Audience Persona Agent.

- TavilySearchClient: Web search via Tavily API
- WebScraperClient: HTTP scraping via httpx + BeautifulSoup
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TavilySearchClient:
    """Web search via Tavily API."""

    def __init__(self) -> None:
        self._client: Any = None

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
        """Search the web and return results."""
        client = self._ensure_client()
        if not client:
            logger.warning("Tavily client not available, returning empty results")
            return []

        try:
            import asyncio

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
