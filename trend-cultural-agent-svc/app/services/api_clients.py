"""External API clients for TCIA: Tavily, WebScraper, OdooRPC."""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TavilySearchClient:
    """Lazy-init async wrapper around the Tavily search SDK."""

    def __init__(self) -> None:
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None and settings.TAVILY_API_KEY:
            try:
                from tavily import TavilyClient

                self._client = TavilyClient(api_key=settings.TAVILY_API_KEY)
            except Exception as exc:
                logger.warning("Failed to initialize Tavily: %s", exc)
        return self._client

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_domains: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search via Tavily. Returns list of result dicts."""
        client = self._ensure_client()
        if not client:
            logger.warning("Tavily not available")
            return []
        try:
            kwargs: dict[str, Any] = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            }
            if include_domains:
                kwargs["include_domains"] = include_domains
            response = await asyncio.to_thread(client.search, **kwargs)
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in response.get("results", [])
            ]
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return []


class WebScraperClient:
    """Async web scraper using httpx + BeautifulSoup."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; BrandAutomator/1.0; "
                    "+https://prevision.ai)"
                )
            },
        )

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def scrape_page(self, url: str) -> str:
        """Scrape a page and return cleaned text (max 10k chars)."""
        if not self._client:
            return ""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)[:10000]
        except Exception as exc:
            logger.warning("Failed to scrape %s: %s", url, exc)
            return ""


class OdooRPCClient:
    """Feature-flagged Odoo CRM access via XML-RPC."""

    def __init__(
        self,
        url: str = "",
        db: str = "",
        username: str = "",
        password: str = "",
    ) -> None:
        self._url = url
        self._db = db
        self._username = username
        self._password = password
        self._uid: int | None = None

    async def authenticate(self) -> int:
        """Authenticate with Odoo. Returns user ID."""
        if self._uid:
            return self._uid
        try:
            import xmlrpc.client

            common = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/common")
            self._uid = await asyncio.to_thread(
                common.authenticate, self._db, self._username, self._password, {}
            )
            return self._uid or 0
        except Exception as exc:
            logger.warning("Odoo authentication failed: %s", exc)
            return 0

    async def search_read(
        self,
        model: str,
        domain: list,
        fields: list[str],
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Search and read records from Odoo."""
        uid = await self.authenticate()
        if not uid:
            return []
        try:
            import xmlrpc.client

            models = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")
            result = await asyncio.to_thread(
                models.execute_kw,
                self._db,
                uid,
                self._password,
                model,
                "search_read",
                [domain],
                {"fields": fields, "limit": limit, "offset": offset},
            )
            return result if isinstance(result, list) else []
        except Exception as exc:
            logger.warning("Odoo search_read failed for %s: %s", model, exc)
            return []

    async def search_count(self, model: str, domain: list) -> int:
        """Count matching records in Odoo."""
        uid = await self.authenticate()
        if not uid:
            return 0
        try:
            import xmlrpc.client

            models = xmlrpc.client.ServerProxy(f"{self._url}/xmlrpc/2/object")
            result = await asyncio.to_thread(
                models.execute_kw,
                self._db,
                uid,
                self._password,
                model,
                "search_count",
                [domain],
            )
            return int(result) if result else 0
        except Exception as exc:
            logger.warning("Odoo search_count failed for %s: %s", model, exc)
            return 0
