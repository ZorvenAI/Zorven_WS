"""SKL-CIA-06: Market Share Estimator — Multi-source proxy estimation."""

import logging
import re
import time
from typing import Any

from app.services.api_clients import TavilySearchClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)


class MarketShareEstimator(BaseSkill):
    """Estimate competitor market share using multi-source proxy data."""

    meta = SkillMeta(
        skill_id="SKL-CIA-06",
        name="market_share_estimator",
        description=(
            "Estimate market share via multi-source proxies: web traffic, "
            "employee count, funding data, review volume. Uses MRA's "
            "market_sizing for TAM/SAM baseline when available."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR", "VIEWER"],
        timeout_ms=45000,
        circuit_breaker_dependency="tavily",
    )

    def __init__(self, tavily_client: TavilySearchClient) -> None:
        self.tavily_client = tavily_client

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Estimate market share for competitors.

        input_data keys:
          - competitors (list): Competitor dicts from SKL-CIA-01
          - industry_context (dict): Optional MRA market data
            - market_sizing: TAM/SAM/SOM from MRA
            - findings: MRA findings
            - industry_trends: MRA trends
        """
        start = time.monotonic()
        competitors = input_data.get("competitors", [])
        industry_context = input_data.get("industry_context", {})
        market_sizing = industry_context.get("market_sizing", {})

        if not competitors:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"market_shares": [], "competitors_analyzed": 0},
                duration_ms=_elapsed(start),
            )

        market_shares: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        for comp in competitors:
            name = comp.get("name", "")
            slug = comp.get("slug", "")

            # Search for company size/funding/traffic data
            query = f"{name} company size employees funding revenue market share"
            results = await self.tavily_client.search(query, max_results=5)

            proxies: dict[str, Any] = {}
            data_sources: list[str] = []

            for r in results:
                content = r.get("content", "")
                url = r.get("url", "")

                if url:
                    sources.append({
                        "type": "web",
                        "title": f"{name} market data - {r.get('title', '')}",
                        "url": url,
                    })

                # Extract employee count
                emp_count = _extract_employee_count(content)
                if emp_count and "employee_count" not in proxies:
                    proxies["employee_count"] = emp_count
                    data_sources.append("employee_data")

                # Extract funding
                funding = _extract_funding(content)
                if funding and "funding" not in proxies:
                    proxies["funding"] = funding
                    data_sources.append("funding_data")

                # Extract revenue hints
                revenue = _extract_revenue(content)
                if revenue and "revenue" not in proxies:
                    proxies["revenue"] = revenue
                    data_sources.append("revenue_data")

            # Calculate relative share estimate
            share_pct, confidence, methodology = _estimate_share(
                proxies, market_sizing
            )

            market_shares.append({
                "slug": slug,
                "name": name,
                "estimated_share_pct": share_pct,
                "confidence": confidence,
                "methodology": methodology,
                "proxies": proxies,
                "data_sources": data_sources,
            })

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "market_shares": market_shares,
                "competitors_analyzed": len(market_shares),
                "market_sizing_available": bool(market_sizing),
                "sources": sources,
            },
            duration_ms=_elapsed(start),
        )


def _extract_employee_count(content: str) -> int | None:
    """Extract employee count from text."""
    patterns = [
        r"(\d{1,3}(?:,\d{3})*)\+?\s*employees",
        r"team\s*of\s*(\d{1,3}(?:,\d{3})*)",
        r"(\d{1,3}(?:,\d{3})*)\s*people",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                continue
    return None


def _extract_funding(content: str) -> str | None:
    """Extract funding amount from text."""
    patterns = [
        r"raised\s*\$?([\d.]+\s*[BMK](?:illion)?)",
        r"funding\s*(?:of|:)?\s*\$?([\d.]+\s*[BMK](?:illion)?)",
        r"\$?([\d.]+\s*[BMK](?:illion)?)\s*(?:in\s+)?(?:funding|raised|round)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_revenue(content: str) -> str | None:
    """Extract revenue hints from text."""
    patterns = [
        r"revenue\s*(?:of|:)?\s*\$?([\d.]+\s*[BMK](?:illion)?)",
        r"\$?([\d.]+\s*[BMK](?:illion)?)\s*(?:in\s+)?(?:revenue|ARR)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _estimate_share(
    proxies: dict[str, Any],
    market_sizing: dict[str, Any],
) -> tuple[float | None, float, str]:
    """Estimate market share from proxy data.

    Returns (share_pct or None, confidence, methodology_description).
    """
    if not proxies:
        return None, 0.1, "No proxy data available"

    # If we have revenue and TAM, compute directly
    revenue = proxies.get("revenue")
    tam = market_sizing.get("tam", {})
    tam_value = tam.get("value", "") if isinstance(tam, dict) else str(tam)

    if revenue and tam_value:
        return (
            None,
            0.4,
            f"Revenue proxy ({revenue}) with TAM ({tam_value}) — manual calc needed",
        )

    # Employee-based rough estimate
    emp_count = proxies.get("employee_count")
    if emp_count:
        # Very rough heuristic: larger companies → larger share
        if emp_count > 10000:
            return 15.0, 0.3, "Employee-based proxy (large enterprise)"
        elif emp_count > 1000:
            return 5.0, 0.3, "Employee-based proxy (mid-size)"
        elif emp_count > 100:
            return 1.0, 0.2, "Employee-based proxy (small-mid)"
        else:
            return 0.5, 0.2, "Employee-based proxy (small)"

    # Funding-based rough estimate
    funding = proxies.get("funding")
    if funding:
        return None, 0.2, f"Funding proxy ({funding}) — relative estimate only"

    return None, 0.1, "Insufficient data for share estimation"


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
