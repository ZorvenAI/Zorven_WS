"""
External API clients for market research data sources.

Three clients:
  - TavilySearchClient: Web search via Tavily SDK
  - WorldBankClient: Economic indicators via World Bank Open Data API
  - GNewsClient: News articles via GNews API
"""

import logging
from typing import Any, Optional

import httpx

from app.cache.redis_manager import RedisManager

logger = logging.getLogger(__name__)


class TavilySearchClient:
    """Web search via Tavily API with market-research query augmentation."""

    def __init__(
        self, api_key: str, redis_manager: Optional[RedisManager] = None
    ) -> None:
        self.api_key = api_key
        self.redis_manager = redis_manager
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy-init Tavily client."""
        if self._client is None and self.api_key:
            from tavily import TavilyClient

            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    async def search(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search the web for market research data.

        Returns list of {title, url, content} dicts.
        Falls back to empty list on failure.
        """
        if not self.api_key:
            logger.info("No Tavily API key — returning empty results")
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


class WorldBankClient:
    """Economic indicators via World Bank Open Data API (no API key needed)."""

    # Common economic indicators
    INDICATORS = {
        "gdp": "NY.GDP.MKTP.CD",
        "gdp_growth": "NY.GDP.MKTP.KD.ZG",
        "inflation": "FP.CPI.TOTL.ZG",
        "unemployment": "SL.UEM.TOTL.ZS",
        "population": "SP.POP.TOTL",
        "gni_per_capita": "NY.GNI.PCAP.CD",
        "trade_pct_gdp": "NE.TRD.GNFS.ZS",
        "fdi_net_inflows": "BX.KLT.DINV.WD.GD.ZS",
    }

    def __init__(
        self, base_url: str, redis_manager: Optional[RedisManager] = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.redis_manager = redis_manager

    async def get_indicator(
        self,
        indicator_id: str,
        country: str = "WLD",
        date_range: str = "2019:2024",
    ) -> list[dict[str, Any]]:
        """
        Fetch an economic indicator from World Bank API.

        Args:
            indicator_id: World Bank indicator code (e.g., NY.GDP.MKTP.CD)
            country: ISO country code or 'WLD' for world
            date_range: Year range (e.g., '2019:2024')

        Returns list of {country, date, value} dicts. Empty on failure.
        """
        # Check cache
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_economic(
                indicator_id, country, date_range
            )
            if cached:
                return cached.get("data", [])

        url = (
            f"{self.base_url}/country/{country}/indicator/{indicator_id}"
            f"?format=json&date={date_range}&per_page=50"
        )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()

            # World Bank returns [metadata, data_array]
            if not isinstance(payload, list) or len(payload) < 2:
                return []

            raw_data = payload[1] or []
            results = []
            for item in raw_data:
                if item.get("value") is not None:
                    results.append(
                        {
                            "country": item.get("country", {}).get("value", country),
                            "date": item.get("date", ""),
                            "value": item["value"],
                            "indicator": item.get("indicator", {}).get("value", ""),
                        }
                    )

            # Cache the results
            if self.redis_manager and results:
                await self.redis_manager.set_cached_economic(
                    indicator_id, country, date_range, {"data": results}
                )

            logger.info(
                "World Bank returned %d data points for %s/%s",
                len(results),
                country,
                indicator_id,
            )
            return results
        except Exception as exc:
            logger.warning("World Bank API error: %s", exc)
            return []

    async def get_multiple_indicators(
        self,
        indicator_names: list[str],
        country: str = "WLD",
        date_range: str = "2019:2024",
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch multiple indicators by friendly name."""
        results: dict[str, list[dict[str, Any]]] = {}
        for name in indicator_names:
            indicator_id = self.INDICATORS.get(name, name)
            data = await self.get_indicator(indicator_id, country, date_range)
            results[name] = data
        return results


class GNewsClient:
    """News articles via GNews API for trend analysis.

    GNews is a free news API that works server-side (no localhost restriction).
    Docs: https://gnews.io/docs/v4
    """

    BASE_URL = "https://gnews.io/api/v4"

    def __init__(
        self, api_key: str, redis_manager: Optional[RedisManager] = None
    ) -> None:
        self.api_key = api_key
        self.redis_manager = redis_manager

    async def search_news(
        self, query: str, max_results: int = 10
    ) -> list[dict[str, Any]]:
        """
        Search for news articles related to a query.

        Returns list of {title, description, url, published_at, source} dicts.
        Falls back to empty list on failure.
        """
        if not self.api_key:
            logger.info("No GNews API key — returning empty results")
            return []

        # Check cache
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_news(query)
            if cached is not None:
                return cached

        try:
            # GNews works best with short keyword queries — trim to 3 words
            words = query.split()
            short_query = " ".join(words[:3]) if len(words) > 3 else query

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/search",
                    params={
                        "q": short_query,
                        "lang": "en",
                        "max": min(max_results, 10),
                        "apikey": self.api_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            articles = data.get("articles", [])
            results = [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "url": a.get("url", ""),
                    "published_at": a.get("publishedAt", ""),
                    "source": a.get("source", {}).get("name", ""),
                }
                for a in articles
                if a.get("title")
            ]

            # Cache results
            if self.redis_manager and results:
                await self.redis_manager.set_cached_news(query, results)

            logger.info("GNews returned %d articles for: %s", len(results), query[:80])
            return results
        except Exception as exc:
            logger.warning("GNews error: %s", exc)
            return []
