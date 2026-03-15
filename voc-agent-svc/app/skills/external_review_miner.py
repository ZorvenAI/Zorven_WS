"""SKL-VoCA-05: External Review Miner — Own product reviews from review platforms."""

import logging
import time
import uuid
from typing import Any

from app.registry.models import ReviewFeedback
from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

# Review platforms to mine
_REVIEW_PLATFORMS = [
    {"name": "G2", "domain": "g2.com"},
    {"name": "Capterra", "domain": "capterra.com"},
    {"name": "Trustpilot", "domain": "trustpilot.com"},
    {"name": "Google Reviews", "domain": "google.com"},
]

# Keywords for extracting pros/cons
_PRO_KEYWORDS = [
    "love",
    "great",
    "excellent",
    "amazing",
    "best",
    "easy to use",
    "helpful",
    "reliable",
    "efficient",
    "intuitive",
    "fast",
    "powerful",
    "recommend",
]

_CON_KEYWORDS = [
    "expensive",
    "slow",
    "buggy",
    "difficult",
    "confusing",
    "poor support",
    "lacking",
    "missing",
    "frustrating",
    "unreliable",
    "complicated",
    "overpriced",
    "wish",
    "downside",
    "con",
]


class ExternalReviewMiner(BaseSkill):
    """Mine tenant's OWN product reviews from G2, Capterra, Trustpilot, Google Reviews."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-05",
        name="external_review_miner",
        description=(
            "Mines the tenant's OWN product reviews from G2, Capterra, "
            "Trustpilot, and Google Reviews. Extracts ratings, pros, cons, "
            "and sentiment signals from verified and unverified reviews."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(
        self,
        tavily_client: TavilySearchClient,
        web_scraper: WebScraperClient,
    ) -> None:
        self.tavily_client = tavily_client
        self.web_scraper = web_scraper

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """
        Mine external review platforms for the tenant's own product reviews.

        input_data keys:
          - company_name (str): Brand/company name to search reviews for
          - prompt (str): Additional search context
        """
        start = time.monotonic()
        company_name = input_data.get("company_name", "")

        if not company_name:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No company_name provided",
                duration_ms=_elapsed(start),
            )

        try:
            own_reviews: list[dict[str, Any]] = []
            sources: list[dict[str, str]] = []

            # Search each review platform
            for platform in _REVIEW_PLATFORMS:
                search_query = f"site:{platform['domain']} {company_name} reviews"
                results = await self.tavily_client.search(search_query, max_results=5)

                for r in results:
                    url = r.get("url", "")
                    content = r.get("content", "")
                    title = r.get("title", "")

                    # Attempt deeper scraping for richer content
                    scraped_content = ""
                    if url:
                        scraped_content = await self.web_scraper.scrape(
                            url, max_chars=3000
                        )

                    full_content = scraped_content or content

                    # Build ReviewFeedback item
                    review = ReviewFeedback(
                        feedback_id=f"review-{uuid.uuid4().hex[:12]}",
                        text=full_content[:2000],
                        platform=platform["name"],
                        review_title=title,
                        pros=_extract_snippets(full_content, _PRO_KEYWORDS),
                        cons=_extract_snippets(full_content, _CON_KEYWORDS),
                        rating=_extract_rating(full_content),
                        verified="verified" in full_content.lower(),
                        metadata={
                            "source_url": url,
                            "platform_domain": platform["domain"],
                        },
                    )
                    own_reviews.append(review.model_dump())

                    if url:
                        sources.append(
                            {
                                "type": "review",
                                "title": title,
                                "url": url,
                                "platform": platform["name"],
                            }
                        )

            logger.info(
                "External review mining for '%s': %d reviews from %d platforms",
                company_name,
                len(own_reviews),
                len(_REVIEW_PLATFORMS),
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "own_reviews": own_reviews,
                    "sources": sources,
                },
                duration_ms=_elapsed(start),
            )

        except Exception as exc:
            logger.error(
                "External review mining failed for '%s': %s",
                company_name,
                exc,
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _extract_snippets(content: str, keywords: list[str]) -> list[str]:
    """Extract text snippets around matching keywords."""
    snippets: list[str] = []
    lower = content.lower()

    for kw in keywords:
        if kw in lower:
            idx = lower.find(kw)
            snippet_start = max(0, idx - 20)
            snippet_end = min(len(content), idx + 120)
            snippet = content[snippet_start:snippet_end].strip()
            if snippet and len(snippet) > 10:
                snippets.append(snippet)

    return snippets[:10]


def _extract_rating(content: str) -> float:
    """Attempt to extract a numeric rating from review content."""
    import re

    patterns = [
        r"(\d(?:\.\d)?)\s*/\s*5",
        r"rated?\s+(\d(?:\.\d)?)\s+out\s+of\s+5",
        r"(\d(?:\.\d)?)\s+stars?",
        r"rating[:\s]+(\d(?:\.\d)?)",
    ]
    lower = content.lower()
    for pattern in patterns:
        match = re.search(pattern, lower)
        if match:
            try:
                val = float(match.group(1))
                if 0 <= val <= 5:
                    return val
            except ValueError:
                continue
    return 0.0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
