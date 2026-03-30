"""SKL-CAA-09: A/B Test Planner.

Builds prompt section for Claude call 2: A/B test plan with test
variables, variants, sample sizes, duration, success metrics.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ABTestPlanner:
    """Build A/B test plan prompt section for Claude call 2."""

    def build_prompt_section(
        self,
        strategy_context: dict[str, Any],
        budget: float = 0.0,
        benchmarks: dict[str, Any] | None = None,
    ) -> str:
        """Build A/B test plan prompt section."""
        section = "## A/B Test Plan Task\n\n"
        section += f"Daily budget: ${budget:.2f}\n\n"

        # Testing budget guidance
        max_test_pct = 20.0
        if budget < 50:
            section += (
                "Budget < $50/day: Limit testing to 1 variable, " "2 variants max.\n"
            )
            max_test_pct = 10.0
        elif budget < 200:
            section += "Budget $50-200/day: Test 2-3 variables, " "2-3 variants each.\n"
            max_test_pct = 15.0
        else:
            section += (
                "Budget >= $200/day: Test up to 4 variables, " "2-4 variants each.\n"
            )

        section += f"Max testing budget: {max_test_pct}% of total\n\n"

        # Testable variables
        section += (
            "### Recommended Test Variables (priority order)\n"
            "1. **Creative format** (image vs video vs carousel)\n"
            "2. **Audience segment** (persona A vs persona B)\n"
            "3. **Ad copy** (benefit-led vs feature-led vs social proof)\n"
            "4. **Placement** (feed vs stories vs reels)\n"
            "5. **Bid strategy** (lowest cost vs cost cap)\n\n"
        )

        # Sample size guidance
        section += (
            "### Statistical Significance\n"
            "- Minimum 100 conversions per variant for reliable results\n"
            "- Run each test for at least 7 days (full weekly cycle)\n"
            "- Minimum 14 days for conversion-based objectives\n\n"
        )

        section += (
            "Output `test_plan` JSON with:\n"
            "- tests: [{variable, variants[], sample_size_per_variant, "
            "duration_days, success_metric, priority}]\n"
            "- total_testing_budget_pct: float (max "
            f"{max_test_pct}%)\n"
            "- total_variants: int\n"
        )

        return section
