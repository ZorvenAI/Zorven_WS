"""External API clients for TCIA: Tavily, WebScraper, OdooRPC."""

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
    """Lazy-init async wrapper around the Tavily search SDK with MCP fallback."""

    def __init__(self, mcp_server_url: str = "") -> None:
        self._client: Any = None
        self._mcp_server_url = mcp_server_url

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
        """Search via MCP (primary) or Tavily SDK (fallback)."""
        # 1. Try MCP if configured
        if self._mcp_server_url and sse_client is not None:
            try:
                results = await self._mcp_search(
                    query, max_results, search_depth,
                    include_domains=include_domains,
                )
                if results:
                    logger.info("MCP search succeeded for: %s", query[:80])
                    return results
            except Exception as exc:
                logger.warning("MCP search failed, falling back to SDK: %s", exc)

        # 2. Fallback to SDK
        return await self._sdk_search(
            query, max_results, search_depth,
            include_domains=include_domains,
        )

    async def _mcp_search(
        self,
        query: str,
        max_results: int,
        search_depth: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search via Tavily MCP Server (SSE transport)."""
        arguments: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
        }
        if kwargs.get("include_domains"):
            arguments["include_domains"] = kwargs["include_domains"]

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
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Search via Tavily Python SDK."""
        client = self._ensure_client()
        if not client:
            logger.warning("Tavily not available")
            return []
        try:
            sdk_kwargs: dict[str, Any] = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            }
            if kwargs.get("include_domains"):
                sdk_kwargs["include_domains"] = kwargs["include_domains"]
            response = await asyncio.to_thread(client.search, **sdk_kwargs)
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
