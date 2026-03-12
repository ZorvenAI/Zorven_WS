"""SKL-CIA-02: Competitor Website Profiler — httpx + BeautifulSoup deep-scrape."""

import logging
import time
from typing import Any

from app.services.api_clients import WebScraperClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class CompetitorWebsiteProfiler(BaseSkill):
    """Deep-scrape competitor websites for messaging, pricing, team signals."""

    meta = SkillMeta(
        skill_id="SKL-CIA-02",
        name="competitor_website_profiler",
        description=(
            "Profile competitor websites: homepage messaging, pricing tiers, "
            "team size signals, feature lists. Max 5 pages per domain (PG-09)."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=60000,
        circuit_breaker_dependency="httpx",
    )

    def __init__(self, web_scraper: WebScraperClient) -> None:
        self.web_scraper = web_scraper

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Profile competitor websites.

        input_data keys:
          - competitors (list): Competitor dicts from SKL-CIA-01 with at least {name, website}
          - prompt (str): Original query for context
        """
        start = time.monotonic()
        competitors = input_data.get("competitors", [])

        if not competitors:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"profiles": [], "competitors_processed": 0},
                duration_ms=_elapsed(start),
            )

        profiles: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for comp in competitors:
            name = comp.get("name", "")
            slug = comp.get("slug", "")
            website = comp.get("website", "")

            if not website:
                profiles.append({
                    "slug": slug,
                    "name": name,
                    "summary": "No website available for profiling",
                    "messaging": "",
                    "value_propositions": [],
                    "pricing_hints": [],
                    "team_size_signal": "",
                    "tech_stack_hints": [],
                })
                continue

            # Scrape homepage
            page_data = await self.web_scraper.scrape_page(website)
            content = page_data.get("content", "")
            title = page_data.get("title", "")

            if page_data.get("url"):
                sources.append({
                    "type": "web",
                    "title": f"{name} - {title}" if title else name,
                    "url": page_data["url"],
                })

            # Extract structured signals from content
            profile = _extract_profile_signals(name, slug, content, title)
            profiles.append(profile)

        logger.info(
            "Profiled %d competitor websites",
            len(profiles),
        )

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "profiles": profiles,
                "competitors_processed": len(profiles),
                "sources": sources,
            },
            duration_ms=_elapsed(start),
        )


def _extract_profile_signals(
    name: str, slug: str, content: str, title: str
) -> dict[str, Any]:
    """Extract structured profile signals from webpage content."""
    content_lower = content.lower()

    # Value propositions — look for short impactful sentences near the top
    value_props: list[str] = []
    for line in content.split("\n")[:30]:
        line = line.strip()
        if 10 < len(line) < 200 and not line.startswith(("©", "Cookie", "Privacy")):
            value_props.append(line)
        if len(value_props) >= 5:
            break

    # Pricing hints
    pricing_hints: list[str] = []
    pricing_keywords = ["pricing", "plans", "free", "enterprise", "starter", "pro"]
    for keyword in pricing_keywords:
        if keyword in content_lower:
            pricing_hints.append(keyword)

    # Team size signals
    team_signal = ""
    team_keywords = [
        ("enterprise", "Large (enterprise-scale)"),
        ("team of", "Mentioned team"),
        ("employees", "Employee count referenced"),
        ("hiring", "Actively hiring"),
        ("careers", "Has careers page"),
    ]
    for keyword, signal in team_keywords:
        if keyword in content_lower:
            team_signal = signal
            break

    # Tech stack hints from content
    tech_hints: list[str] = []
    tech_keywords = [
        "react", "python", "aws", "azure", "gcp", "kubernetes",
        "docker", "api", "saas", "cloud", "machine learning", "ai",
    ]
    for tk in tech_keywords:
        if tk in content_lower:
            tech_hints.append(tk)

    return {
        "slug": slug,
        "name": name,
        "summary": content[:500] if content else "Unable to scrape content",
        "messaging": title,
        "value_propositions": value_props[:5],
        "pricing_hints": pricing_hints,
        "team_size_signal": team_signal,
        "tech_stack_hints": tech_hints[:10],
    }


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
