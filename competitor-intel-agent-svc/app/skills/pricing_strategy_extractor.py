"""SKL-CIA-05: Pricing Strategy Extractor — httpx structured extraction."""

import logging
import re
import time
from typing import Any

from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class PricingStrategyExtractor(BaseSkill):
    """Extract competitor pricing tiers and models."""

    meta = SkillMeta(
        skill_id="SKL-CIA-05",
        name="pricing_strategy_extractor",
        description=(
            "Extract pricing intelligence: model type, tier names, prices, "
            "feature gating, billing frequency."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="httpx",
    )

    def __init__(
        self,
        web_scraper: WebScraperClient,
        tavily_client: TavilySearchClient,
    ) -> None:
        self.web_scraper = web_scraper
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Extract pricing strategy for competitors.

        input_data keys:
          - competitors (list): Competitor dicts with {name, slug, website}
          - prompt (str): Original query
        """
        start = time.monotonic()
        competitors = input_data.get("competitors", [])

        if not competitors:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"pricing_data": [], "competitors_analyzed": 0},
                duration_ms=_elapsed(start),
            )

        pricing_data: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for comp in competitors:
            name = comp.get("name", "")
            slug = comp.get("slug", "")
            website = comp.get("website", "")

            pricing_content = ""

            # Try scraping pricing page directly
            if website:
                pricing_urls = [
                    f"{website.rstrip('/')}/pricing",
                    f"{website.rstrip('/')}/plans",
                ]
                for url in pricing_urls:
                    page = await self.web_scraper.scrape_page(url)
                    if page.get("content"):
                        pricing_content = page["content"]
                        sources.append({
                            "type": "pricing",
                            "title": f"{name} pricing page",
                            "url": url,
                        })
                        break

            # Fallback to Tavily search for pricing info
            if not pricing_content:
                results = await self.tavily_client.search(
                    f"{name} pricing plans cost", max_results=5
                )
                for r in results:
                    content = r.get("content", "")
                    if any(
                        kw in content.lower()
                        for kw in ["pricing", "plan", "cost", "month", "year", "$"]
                    ):
                        pricing_content = content
                        url = r.get("url", "")
                        if url:
                            sources.append({
                                "type": "pricing",
                                "title": f"{name} pricing - {r.get('title', '')}",
                                "url": url,
                            })
                        break

            # Extract structured pricing
            pricing = _extract_pricing(name, slug, pricing_content)
            pricing_data.append(pricing)

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "pricing_data": pricing_data,
                "competitors_analyzed": len(pricing_data),
                "sources": sources,
            },
            duration_ms=_elapsed(start),
        )


def _extract_pricing(name: str, slug: str, content: str) -> dict[str, Any]:
    """Extract structured pricing data from page content."""
    content_lower = content.lower()

    # Detect model type
    model_type = "unknown"
    model_keywords = {
        "subscription": ["subscription", "monthly", "annually", "/month", "/year"],
        "usage_based": ["usage", "pay as you go", "per unit", "metered"],
        "freemium": ["free plan", "free tier", "freemium", "free forever"],
        "one_time": ["one-time", "lifetime", "perpetual"],
    }
    for model, keywords in model_keywords.items():
        if any(kw in content_lower for kw in keywords):
            model_type = model
            break

    # Detect tier names
    tiers: list[dict[str, Any]] = []
    tier_keywords = [
        "free", "starter", "basic", "pro", "professional",
        "business", "enterprise", "team", "growth", "premium",
    ]
    for tier_name in tier_keywords:
        if tier_name in content_lower:
            # Try to find associated price
            price = _find_price_near_keyword(content, tier_name)
            tiers.append({
                "name": tier_name.capitalize(),
                "price": price,
            })

    # Detect pricing amounts
    has_free = "free" in content_lower and (
        "free plan" in content_lower
        or "free tier" in content_lower
        or "free forever" in content_lower
    )
    has_enterprise = "enterprise" in content_lower or "contact" in content_lower

    # Currency detection
    currency = "USD"
    if "€" in content or "eur" in content_lower:
        currency = "EUR"
    elif "£" in content:
        currency = "GBP"

    return {
        "slug": slug,
        "name": name,
        "model_type": model_type,
        "tiers": tiers[:6],
        "has_free_tier": has_free,
        "has_enterprise": has_enterprise,
        "currency": currency,
        "summary": (
            f"{name}: {model_type} model, "
            f"{len(tiers)} tiers detected, "
            f"{'free tier available' if has_free else 'no free tier'}"
        ),
    }


def _find_price_near_keyword(content: str, keyword: str) -> str:
    """Find a price amount near a tier keyword."""
    # Find the keyword position
    idx = content.lower().find(keyword)
    if idx == -1:
        return ""

    # Look in a window around the keyword
    window = content[max(0, idx - 50): idx + 200]
    price_patterns = [
        r"\$(\d+(?:,\d{3})*(?:\.\d{2})?)",
        r"(\d+(?:,\d{3})*(?:\.\d{2})?)\s*/\s*(?:mo|month|yr|year)",
    ]
    for pattern in price_patterns:
        match = re.search(pattern, window)
        if match:
            return f"${match.group(1)}"
    return ""


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
