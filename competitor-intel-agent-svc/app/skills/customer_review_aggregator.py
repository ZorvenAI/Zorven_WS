"""SKL-CIA-04: Customer Review Aggregator — Tavily search for G2/Capterra/Trustpilot."""

import logging
import re
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class CustomerReviewAggregator(BaseSkill):
    """Aggregate competitor reviews from G2, Capterra, Trustpilot."""

    meta = SkillMeta(
        skill_id="SKL-CIA-04",
        name="customer_review_aggregator",
        description=(
            "Aggregate customer reviews from G2, Capterra, Trustpilot. "
            "Extract average rating, sentiment, praise/complaint themes."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Aggregate customer reviews for competitors.

        input_data keys:
          - competitors (list): Competitor dicts with {name, slug}
          - prompt (str): Original query
        """
        start = time.monotonic()
        competitors = input_data.get("competitors", [])

        if not competitors:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"reviews": [], "competitors_analyzed": 0},
                duration_ms=_elapsed(start),
            )

        reviews: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for comp in competitors:
            name = comp.get("name", "")
            slug = comp.get("slug", "")

            query = f"{name} reviews G2 Capterra Trustpilot rating"
            results = await self.tavily_client.search(query, max_results=8)

            rating_values: list[float] = []
            praise_themes: list[str] = []
            complaint_themes: list[str] = []
            review_sources: list[str] = []

            for r in results:
                url = r.get("url", "")
                content = r.get("content", "")

                if url:
                    sources.append({
                        "type": "review",
                        "title": f"{name} reviews - {r.get('title', '')}",
                        "url": url,
                    })

                # Detect review platform
                for platform in ["g2.com", "capterra.com", "trustpilot.com"]:
                    if platform in url:
                        review_sources.append(platform)

                # Extract ratings
                extracted_ratings = _extract_ratings(content)
                rating_values.extend(extracted_ratings)

                # Extract sentiment themes
                praises, complaints = _extract_sentiment_themes(content)
                praise_themes.extend(praises)
                complaint_themes.extend(complaints)

            # Compute averages
            avg_rating = (
                round(sum(rating_values) / len(rating_values), 1)
                if rating_values
                else None
            )

            reviews.append({
                "slug": slug,
                "name": name,
                "avg_rating": avg_rating,
                "total_reviews_estimated": len(rating_values) * 50,  # rough proxy
                "sentiment_breakdown": {
                    "positive": len(praise_themes),
                    "negative": len(complaint_themes),
                },
                "top_praise_themes": list(set(praise_themes))[:5],
                "top_complaint_themes": list(set(complaint_themes))[:5],
                "review_sources": list(set(review_sources)),
                "data_completeness_score": min(
                    1.0, len(results) / 5
                ),
                "summary": (
                    f"{name}: {'%.1f' % avg_rating if avg_rating else 'N/A'}/5 "
                    f"across {len(set(review_sources))} platforms"
                ),
            })

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "reviews": reviews,
                "competitors_analyzed": len(reviews),
                "sources": sources,
            },
            duration_ms=_elapsed(start),
        )


def _extract_ratings(content: str) -> list[float]:
    """Extract numerical ratings from review content."""
    ratings: list[float] = []
    patterns = [
        r"(\d\.?\d?)\s*/\s*5",
        r"rated?\s*(\d\.?\d?)\s*(?:out of 5|/5|stars)",
        r"(\d\.?\d?)\s*stars?",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            try:
                val = float(match.group(1))
                if 1.0 <= val <= 5.0:
                    ratings.append(val)
            except ValueError:
                continue
    return ratings


def _extract_sentiment_themes(content: str) -> tuple[list[str], list[str]]:
    """Extract praise and complaint themes from review content."""
    content_lower = content.lower()
    praises: list[str] = []
    complaints: list[str] = []

    praise_keywords = {
        "easy to use": "ease_of_use",
        "great support": "customer_support",
        "intuitive": "usability",
        "powerful": "feature_richness",
        "reliable": "reliability",
        "fast": "performance",
        "excellent": "quality",
        "love": "satisfaction",
        "recommended": "recommendation",
    }
    complaint_keywords = {
        "expensive": "pricing",
        "slow": "performance",
        "buggy": "reliability",
        "confusing": "usability",
        "poor support": "customer_support",
        "missing feature": "feature_gaps",
        "difficult": "learning_curve",
        "limited": "limitations",
        "crash": "stability",
    }

    for keyword, theme in praise_keywords.items():
        if keyword in content_lower:
            praises.append(theme)
    for keyword, theme in complaint_keywords.items():
        if keyword in content_lower:
            complaints.append(theme)

    return praises, complaints


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
