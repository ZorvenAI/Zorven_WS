"""SKL-CAA-08: Placement Budget Builder.

Builds prompt section for Claude call 1: placement strategy per ad set,
CBO vs ABO decision, budget allocation, bid strategy.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Meta placement options
META_PLACEMENTS = [
    "facebook_feed",
    "facebook_right_column",
    "facebook_stories",
    "facebook_reels",
    "facebook_marketplace",
    "instagram_feed",
    "instagram_stories",
    "instagram_reels",
    "instagram_explore",
    "audience_network",
    "messenger_inbox",
    "messenger_stories",
]


class PlacementBudgetBuilder:
    """Build placement and budget prompt section for Claude call 1."""

    def build_prompt_section(
        self,
        strategy_context: dict[str, Any],
        budget: float = 0.0,
        benchmarks: dict[str, Any] | None = None,
    ) -> str:
        """Build placement and budget allocation prompt section."""
        maturity = strategy_context.get("brand_maturity", "new")

        section = "## Placement & Budget Allocation Task\n\n"
        section += f"Daily campaign budget: **${budget:.2f}**\n"
        section += f"Brand maturity: **{maturity}**\n\n"

        # CBO vs ABO guidance
        section += "### Campaign Budget Optimization (CBO) vs Ad Set Budget (ABO)\n"
        if budget >= 100:
            section += (
                "Budget >= $100/day: CBO recommended for efficiency.\n"
                "Use ABO only for strict A/B test isolation.\n"
            )
        else:
            section += (
                "Budget < $100/day: ABO recommended for precise control.\n"
                "CBO may over-concentrate spend on fewer ad sets.\n"
            )
        section += "\n"

        # Placement options
        section += "### Available Meta Placements\n"
        for p in META_PLACEMENTS:
            section += f"- `{p}`\n"
        section += "\n"

        # Bid strategy guidance
        section += "### Bid Strategies\n"
        section += (
            "- `LOWEST_COST`: No bid cap (default, good for awareness)\n"
            "- `COST_CAP`: Target CPA cap (good for conversions)\n"
            "- `BID_CAP`: Maximum bid per auction\n"
            "- `MINIMUM_ROAS`: Target ROAS (good for e-commerce)\n\n"
        )

        # Benchmarks for budget planning
        if benchmarks and benchmarks.get("benchmarks"):
            bm = benchmarks["benchmarks"]
            cpm = bm.get("cpm", {}).get("mid", 12.0)
            section += (
                f"Industry avg CPM: ${cpm:.2f} "
                f"→ ~{int(budget / cpm * 1000):,} daily impressions "
                f"at current budget\n\n"
            )

        section += (
            "Output `placement_budget` JSON with:\n"
            "- cbo_enabled: bool\n"
            "- bid_strategy: string\n"
            "- per_ad_set: [{ad_set_name, placements[], daily_budget, "
            "optimization_goal}]\n"
        )

        return section
