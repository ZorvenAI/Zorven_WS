"""SKL-CIA-01: Competitor Discovery Search — Tavily web search."""

import logging
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class CompetitorDiscoverySearch(BaseSkill):
    """Identifies competitors via Tavily web search, optionally seeded by MRA data."""

    meta = SkillMeta(
        skill_id="SKL-CIA-01",
        name="competitor_discovery_search",
        description=(
            "Discover competitors via web search. Uses MRA competitive_landscape "
            "as seed hints when available from upstream pipeline."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Discover competitors via web search.

        input_data keys:
          - query (str): User's analysis query
          - industry (str): Industry/sector
          - geography (str): Geographic scope
          - max_competitors (int): Max competitors to discover (default 10, cap 20)
          - mra_competitors (list): Pre-identified from MRA's competitive_landscape
          - market_context (dict): Market overview from MRA
          - search_queries (list): Specific search queries from plan
        """
        start = time.monotonic()
        query = input_data.get("query", "")
        industry = input_data.get("industry", "")
        geography = input_data.get("geography", "")
        max_competitors = min(input_data.get("max_competitors", 10), 20)
        mra_competitors = input_data.get("mra_competitors", [])
        search_queries = input_data.get("search_queries", [])

        if not query:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No query provided",
                duration_ms=_elapsed(start),
            )

        # Start with MRA seeds (already identified by upstream agent)
        competitors: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        for mra_comp in mra_competitors:
            name = mra_comp.get("name", "")
            if name and name.lower() not in seen_names:
                seen_names.add(name.lower())
                competitors.append({
                    "name": name,
                    "slug": _slugify(name),
                    "description": mra_comp.get("description", ""),
                    "market_position": mra_comp.get("market_position", ""),
                    "website": mra_comp.get("website", ""),
                    "confidence": 0.7,
                    "source": "mra_upstream",
                })

        # Build search queries — always include geography when specified
        geo_suffix = f" in {geography}" if geography else ""
        if not search_queries:
            search_queries = [f"{query}{geo_suffix}"]
            if industry:
                search_queries.append(
                    f"top competitors in {industry}{geo_suffix}"
                )
            search_queries.append(f"{query} competitors alternatives{geo_suffix}")
        elif geography:
            # Ensure plan-generated queries include geography if not already present
            geo_lower = geography.lower()
            search_queries = [
                q if geo_lower in q.lower() else f"{q} {geography}"
                for q in search_queries
            ]

        # Execute Tavily searches
        all_results: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []
        for sq in search_queries[:4]:
            results = await self.tavily_client.search(sq, max_results=10)
            for r in results:
                all_results.append(r)
                url = r.get("url", "")
                if url:
                    sources.append({
                        "type": "web",
                        "title": r.get("title", ""),
                        "url": url,
                    })

        # Extract competitor names from search results
        for result in all_results:
            if len(competitors) >= max_competitors:
                break
            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")

            # Simple heuristic: extract company names from titles
            extracted = _extract_company_hints(title, content)
            for comp_name in extracted:
                if (
                    comp_name.lower() not in seen_names
                    and len(competitors) < max_competitors
                ):
                    seen_names.add(comp_name.lower())
                    competitors.append({
                        "name": comp_name,
                        "slug": _slugify(comp_name),
                        "description": content[:200] if content else "",
                        "market_position": "",
                        "website": url,
                        "confidence": 0.5,
                        "source": "tavily_search",
                    })

        logger.info(
            "Discovered %d competitors (%d from MRA, %d from search)",
            len(competitors),
            len(mra_competitors),
            len(competitors) - len(mra_competitors),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "competitors": competitors,
                "search_queries_used": search_queries[:4],
                "total_search_results": len(all_results),
                "mra_seeds_count": len(mra_competitors),
                "sources": sources,
            },
            duration_ms=_elapsed(start),
        )


def _slugify(name: str) -> str:
    """Convert a company name to a URL-safe slug."""
    import re

    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "unknown"


def _extract_company_hints(title: str, content: str) -> list[str]:
    """Extract potential company names from search result text.

    Simple heuristic — looks for capitalized multi-word sequences
    near competitor-related keywords.
    """
    import re

    hints: list[str] = []
    text = f"{title} {content[:500]}"
    # Look for "Company vs Company" or "Company - Description" patterns
    vs_match = re.findall(r"([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)\s+vs\.?\s+", text)
    hints.extend(vs_match)

    # Look for capitalized proper nouns near "competitor" keywords
    comp_keywords = ["competitor", "alternative", "versus", "vs", "compared"]
    for keyword in comp_keywords:
        if keyword.lower() in text.lower():
            # Find nearby capitalized words
            nearby = re.findall(
                r"([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2})",
                text[:300],
            )
            hints.extend(nearby)
            break

    # Deduplicate and filter
    seen: set[str] = set()
    result: list[str] = []
    stop_words = {
        "The", "This", "That", "What", "How", "Why", "Top", "Best",
        "New", "Free", "Get", "Our", "Your", "About", "Home",
    }
    for h in hints:
        h = h.strip()
        if h and h not in seen and h not in stop_words and len(h) > 2:
            seen.add(h)
            result.append(h)
    return result[:5]


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
