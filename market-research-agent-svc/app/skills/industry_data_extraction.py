"""SKL-MRA-02: Industry Data Extraction — Structured data via Tavily."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class IndustryDataExtraction(BaseSkill):
    """Extracts structured industry data using Tavily with raw content."""

    meta = SkillMeta(
        skill_id="SKL-MRA-02",
        name="industry_data_extraction",
        description="Extract structured industry data from web sources",
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=30000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Extract industry data from web sources.

        input_data keys:
          - queries (list[str]): Extraction queries
          - extraction_focus (str): What to focus extraction on
          - max_results (int): Max results per query (default 5)
        """
        start = time.monotonic()
        queries = input_data.get("queries", [])
        extraction_focus = input_data.get("extraction_focus", "")
        max_results = input_data.get("max_results", 5)

        if not queries:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No queries provided",
                duration_ms=_elapsed(start),
            )

        try:
            all_data: list[dict[str, Any]] = []
            sources: list[dict[str, str]] = []
            seen_urls: set[str] = set()

            for query in queries[:4]:
                augmented = query
                if extraction_focus:
                    augmented = f"{query} {extraction_focus}"

                results = await self.tavily_client.search(
                    augmented, max_results=max_results
                )
                for r in results:
                    url = r.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_data.append(
                            {
                                "title": r.get("title", ""),
                                "content": r.get("content", ""),
                                "url": url,
                                "score": r.get("score", 0.0),
                            }
                        )
                        sources.append({"title": r.get("title", ""), "url": url})

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "extracted_data": all_data,
                    "raw_context": "\n\n".join(d.get("content", "") for d in all_data),
                    "sources": sources,
                    "extraction_count": len(all_data),
                },
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("IndustryDataExtraction failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
