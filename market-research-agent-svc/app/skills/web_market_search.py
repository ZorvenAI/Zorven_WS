"""SKL-MRA-01: Web Market Search — Tavily + GNews web search."""

import logging
import time
from typing import Any

from app.services.api_clients import GNewsClient, TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class WebMarketSearch(BaseSkill):
    """Searches web for market data using Tavily and GNews."""

    meta = SkillMeta(
        skill_id="SKL-MRA-01",
        name="web_market_search",
        description="Web search for market data, reports, and news articles",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=30000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(
        self,
        tavily_client: TavilySearchClient,
        gnews_client: GNewsClient,
    ) -> None:
        self.tavily_client = tavily_client
        self.gnews_client = gnews_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Execute web search.

        input_data keys:
          - query (str): Search query
          - focus_areas (list[str]): Areas to focus on
          - geography (str): Geographic scope
          - max_results (int): Max results per source (default 5)
          - include_news (bool): Include GNews results (default True)
        """
        start = time.monotonic()
        query = input_data.get("query", "")
        focus_areas = input_data.get("focus_areas", [])
        geography = input_data.get("geography", "")
        max_results = input_data.get("max_results", 5)
        include_news = input_data.get("include_news", True)

        if not query:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided",
                duration_ms=_elapsed(start),
            )

        # Augment query with geography if specified
        search_query = query
        if geography:
            search_query = f"{query} {geography}"

        try:
            # Search via Tavily
            web_results = await self.tavily_client.search(
                search_query, max_results=max_results
            )

            # Optionally search GNews
            news_results: list[dict[str, Any]] = []
            if include_news:
                news_results = await self.gnews_client.search_news(
                    search_query, max_results=max_results
                )

            # Deduplicate by URL
            seen_urls: set[str] = set()
            unique_results: list[dict[str, Any]] = []
            for r in web_results + news_results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_results.append(r)

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "results": unique_results,
                    "query_used": search_query,
                    "source_count": len(unique_results),
                    "web_count": len(web_results),
                    "news_count": len(news_results),
                    "focus_areas": focus_areas,
                },
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("WebMarketSearch failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
