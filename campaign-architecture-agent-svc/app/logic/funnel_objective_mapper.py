"""SKL-CAA-06: Funnel Objective Mapper.

Builds prompt section for Claude call 1: funnel stage -> Meta objective
mapping, budget % allocation per stage, brand maturity assessment.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Meta Marketing API campaign objectives
META_OBJECTIVES = {
    "AWARENESS": "Reach and brand awareness",
    "TRAFFIC": "Drive traffic to destination",
    "ENGAGEMENT": "Post engagement, page likes, event responses",
    "LEADS": "Lead generation forms",
    "APP_PROMOTION": "App installs and events",
    "SALES": "Conversions, catalog sales",
}

# Default funnel-to-objective mapping by brand maturity
_FUNNEL_DEFAULTS = {
    "new": {
        "tofu": {"objective": "AWARENESS", "budget_pct": 50},
        "mofu": {"objective": "TRAFFIC", "budget_pct": 30},
        "bofu": {"objective": "LEADS", "budget_pct": 15},
        "retention": {"objective": "ENGAGEMENT", "budget_pct": 5},
    },
    "emerging": {
        "tofu": {"objective": "AWARENESS", "budget_pct": 35},
        "mofu": {"objective": "TRAFFIC", "budget_pct": 30},
        "bofu": {"objective": "SALES", "budget_pct": 25},
        "retention": {"objective": "ENGAGEMENT", "budget_pct": 10},
    },
    "established": {
        "tofu": {"objective": "AWARENESS", "budget_pct": 20},
        "mofu": {"objective": "ENGAGEMENT", "budget_pct": 25},
        "bofu": {"objective": "SALES", "budget_pct": 40},
        "retention": {"objective": "ENGAGEMENT", "budget_pct": 15},
    },
}


class FunnelObjectiveMapper:
    """Build funnel mapping prompt section for Claude call 1."""

    def build_prompt_section(
        self,
        strategy_context: dict[str, Any],
        budget: float = 0.0,
    ) -> str:
        """Build funnel-objective mapping prompt section."""
        maturity = strategy_context.get("brand_maturity", "new")
        defaults = _FUNNEL_DEFAULTS.get(maturity, _FUNNEL_DEFAULTS["new"])

        section = "## Funnel-Objective Mapping Task\n\n"
        section += (
            f"Brand maturity level: **{maturity}**\n"
            f"Daily budget: **${budget:.2f}**\n\n"
        )
        section += "Design a funnel map with these stages:\n"
        for stage, cfg in defaults.items():
            section += (
                f"- **{stage.upper()}**: Default Meta objective = "
                f"{cfg['objective']}, default budget = "
                f"{cfg['budget_pct']}%\n"
            )

        section += "\nAvailable Meta objectives:\n"
        for obj, desc in META_OBJECTIVES.items():
            section += f"- `{obj}`: {desc}\n"

        section += (
            "\nOutput a `funnel_map` JSON with stages array, "
            "each containing: stage, meta_objective, budget_pct, "
            "description. Budget percentages must sum to 100.\n"
        )

        # Add positioning context for objective selection
        positioning = strategy_context.get("positioning", {})
        if positioning.get("statement"):
            section += f"\nBrand positioning: {positioning['statement']}\n"

        return section
