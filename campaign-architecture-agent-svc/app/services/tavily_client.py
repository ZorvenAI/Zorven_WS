"""Tavily web research client for industry benchmarks and competitor ads.

Stub mode when CAA_TAVILY_API_KEY is empty — returns empty results.
Results are cached in Redis (24h for benchmarks, 12h for competitor ads).
"""

import hashlib
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class TavilyClient:
    """Direct httpx-based Tavily search client with Redis caching."""

    TAVILY_SEARCH_URL = "https://api.tavily.com/search"

    def __init__(
        self,
        api_key: str = "",
        redis_manager: Any = None,
        benchmark_cache_ttl: int = 86400,
        competitor_cache_ttl: int = 43200,
    ):
        self._api_key = api_key
        self._redis = redis_manager
        self._benchmark_ttl = benchmark_cache_ttl
        self._competitor_ttl = competitor_cache_ttl

    @property
    def enabled(self) -> bool:
        """Whether Tavily is configured."""
        return bool(self._api_key)

    async def search_benchmarks(
        self, industry: str, region: str = "global"
    ) -> dict[str, Any]:
        """Search for industry advertising benchmarks.

        Returns CPM, CTR, CPC, CPA, ROAS benchmarks.
        Returns empty dict in stub mode.
        """
        if not self._api_key:
            logger.info("Tavily stub mode: skipping benchmark search")
            return {}

        cache_key = (
            f"caa:benchmarks:{hashlib.md5(f'{industry}:{region}'.encode()).hexdigest()}"
        )

        # Check cache
        if self._redis:
            cached = await self._redis.get_json(cache_key)
            if cached:
                logger.info("Tavily benchmark cache hit for %s", industry)
                return cached

        query = (
            f"{industry} advertising benchmarks 2024 2025 "
            f"Meta Facebook ads CPM CTR CPC CPA ROAS {region}"
        )
        results = await self._search(query, max_results=5)

        if results and self._redis:
            await self._redis.set_json(cache_key, results, ttl=self._benchmark_ttl)

        return results

    async def search_competitor_ads(
        self, competitors: list[str], industry: str = ""
    ) -> dict[str, Any]:
        """Search for competitor advertising patterns.

        Returns competitor ad strategies, formats, messaging.
        Returns empty dict in stub mode.
        """
        if not self._api_key:
            logger.info("Tavily stub mode: skipping competitor ad search")
            return {}

        comp_str = ", ".join(competitors[:5])
        cache_key = f"caa:competitors:{hashlib.md5(comp_str.encode()).hexdigest()}"

        # Check cache
        if self._redis:
            cached = await self._redis.get_json(cache_key)
            if cached:
                logger.info("Tavily competitor cache hit for %s", comp_str)
                return cached

        query = (
            f"{comp_str} Meta Facebook advertising strategy "
            f"ad formats {industry} 2024 2025"
        )
        results = await self._search(query, max_results=5)

        if results and self._redis:
            await self._redis.set_json(cache_key, results, ttl=self._competitor_ttl)

        return results

    async def _search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        """Execute a Tavily search query."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TAVILY_SEARCH_URL,
                    json={
                        "api_key": self._api_key,
                        "query": query,
                        "search_depth": "advanced",
                        "max_results": max_results,
                        "include_answer": True,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "answer": data.get("answer", ""),
                    "results": [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", ""),
                            "score": r.get("score", 0),
                        }
                        for r in data.get("results", [])
                    ],
                    "query": query,
                }
        except Exception as exc:
            logger.warning("Tavily search failed: %s", exc)
            return {}
