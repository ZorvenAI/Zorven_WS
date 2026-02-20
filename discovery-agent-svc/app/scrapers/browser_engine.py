"""
Browser engine — URL scraping via httpx with Redis page caching.

Uses httpx.AsyncClient for HTTP fetching. Returns raw HTML and
content-type header for downloadable file detection.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.cache.redis_manager import RedisManager

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; DiscoveryAgent/1.0; "
    "+https://github.com/prevision/discovery-agent-svc)"
)


@dataclass
class ScrapeResult:
    """Result of a scrape operation."""

    html: str
    content_type: str
    status_code: int


class BrowserEngine:
    """URL scraper using httpx with Redis page caching."""

    def __init__(
        self,
        timeout: int = 30,
        redis_manager: Optional[RedisManager] = None,
    ) -> None:
        self.timeout = timeout
        self.redis_manager = redis_manager

    async def scrape(self, url: str, tenant_id: str = "") -> ScrapeResult:
        """
        Scrape a URL and return the content.

        Checks Redis page cache first. On HTTP error, returns
        empty content gracefully.
        """
        # Check page cache for cleaned Markdown
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_page(url)
            if cached is not None:
                return ScrapeResult(
                    html=cached,
                    content_type="text/markdown",
                    status_code=200,
                )

        # Fetch the page
        try:
            async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                )
                response.raise_for_status()

                content_type = response.headers.get("content-type", "text/html")
                return ScrapeResult(
                    html=response.text,
                    content_type=content_type,
                    status_code=response.status_code,
                )

        except httpx.TimeoutException:
            logger.warning("Timeout scraping %s", url)
            return ScrapeResult(html="", content_type="", status_code=0)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "HTTP %d scraping %s", exc.response.status_code, url
            )
            return ScrapeResult(
                html="", content_type="", status_code=exc.response.status_code
            )
        except httpx.HTTPError as exc:
            logger.warning("Error scraping %s: %s", url, exc)
            return ScrapeResult(html="", content_type="", status_code=0)
