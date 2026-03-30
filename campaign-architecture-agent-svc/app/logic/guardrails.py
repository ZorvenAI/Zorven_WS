"""Campaign Architecture Guardrails.

Input guardrails (IG):
- IG-11: Budget sanity ($10 min, cap max)
- IG-12: Special Ad Category detection (housing/employment/credit)

Plan guardrails (PG):
- PG-06: Budget allocation validation (100% ±1%)
- PG-07: Audience overlap detection (>50%)
- PG-08: KPI realism check (vs benchmarks)
- PG-09: Test sample size guard
- PG-10: Placement-objective compatibility

Output guardrails (OG):
- OG-06: Meta API schema validation
- OG-08: Budget cap verification
"""

import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# Special Ad Category keywords
_HOUSING_KEYWORDS = [
    "real estate",
    "housing",
    "mortgage",
    "apartment",
    "rental",
    "property",
    "home loan",
]
_EMPLOYMENT_KEYWORDS = [
    "job",
    "hiring",
    "recruitment",
    "career",
    "employment",
    "staffing",
]
_CREDIT_KEYWORDS = [
    "credit",
    "loan",
    "lending",
    "finance",
    "insurance",
    "banking",
    "financial services",
]

# Valid Meta campaign objectives
_VALID_OBJECTIVES = {
    "AWARENESS",
    "TRAFFIC",
    "ENGAGEMENT",
    "LEADS",
    "APP_PROMOTION",
    "SALES",
}

# Placement-objective compatibility
_PLACEMENT_RESTRICTIONS = {
    "APP_PROMOTION": {"audience_network"},
    "LEADS": {
        "facebook_feed",
        "instagram_feed",
        "facebook_stories",
        "instagram_stories",
    },
}


class InputGuardrails:
    """Validate inputs before analysis begins."""

    def check_budget_sanity(self, budget: float) -> dict[str, Any]:
        """IG-11: Validate budget is within acceptable range."""
        issues = []
        if budget < settings.MIN_DAILY_BUDGET:
            issues.append(
                f"Budget ${budget:.2f}/day below Meta minimum "
                f"(${settings.MIN_DAILY_BUDGET})"
            )
        if budget > settings.DEFAULT_DAILY_BUDGET_CAP:
            issues.append(
                f"Budget ${budget:.2f}/day exceeds configured cap "
                f"(${settings.DEFAULT_DAILY_BUDGET_CAP})"
            )
        return {"valid": len(issues) == 0, "issues": issues}

    def detect_special_ad_category(
        self, company_context: dict[str, Any] | None, prompt: str = ""
    ) -> str:
        """IG-12: Detect if Special Ad Category applies.

        Returns: "HOUSING", "EMPLOYMENT", "CREDIT", or "NONE"
        """
        text = prompt.lower()
        if company_context:
            text += " " + company_context.get("industry", "").lower()
            text += " " + company_context.get("description", "").lower()

        for kw in _HOUSING_KEYWORDS:
            if kw in text:
                return "HOUSING"
        for kw in _EMPLOYMENT_KEYWORDS:
            if kw in text:
                return "EMPLOYMENT"
        for kw in _CREDIT_KEYWORDS:
            if kw in text:
                return "CREDIT"
        return "NONE"


class PlanGuardrails:
    """Validate the campaign plan after LLM call 1."""

    def check_budget_allocation(self, funnel_map: dict[str, Any]) -> dict[str, Any]:
        """PG-06: Budget percentages must sum to 100% (±1%)."""
        stages = funnel_map.get("stages", [])
        total = sum(s.get("budget_pct", 0) for s in stages)
        valid = 99.0 <= total <= 101.0
        if not valid:
            return {
                "valid": False,
                "issue": f"Budget allocation sums to {total:.1f}% (must be 99-101%)",
            }
        return {"valid": True}

    def check_audience_overlap(
        self, targeting_specs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """PG-07: Detect audience overlap > 50% between ad sets."""
        overlaps = []
        for i, spec_a in enumerate(targeting_specs):
            for spec_b in targeting_specs[i + 1 :]:
                interests_a = set(spec_a.get("interests", []))
                interests_b = set(spec_b.get("interests", []))
                if interests_a and interests_b:
                    overlap = interests_a & interests_b
                    overlap_pct = (
                        len(overlap) / min(len(interests_a), len(interests_b))
                        if min(len(interests_a), len(interests_b)) > 0
                        else 0
                    )
                    if overlap_pct > 0.5:
                        overlaps.append(
                            {
                                "ad_sets": [
                                    spec_a.get("ad_set_name", ""),
                                    spec_b.get("ad_set_name", ""),
                                ],
                                "overlap_pct": round(overlap_pct * 100, 1),
                            }
                        )
        return {
            "valid": len(overlaps) == 0,
            "overlaps": overlaps,
        }

    def check_kpi_realism(
        self,
        kpi_targets: dict[str, Any],
        benchmarks: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """PG-08: KPI targets should be within 2x of industry benchmarks."""
        if not benchmarks:
            return {"valid": True, "note": "No benchmarks for comparison"}

        issues = []
        bm = benchmarks.get("benchmarks", {})
        per_funnel = kpi_targets.get("targets", {})
        for stage, kpis in per_funnel.items():
            for metric in ["cpm", "ctr", "cpc", "cpa", "roas"]:
                target = kpis.get(metric, 0)
                bm_high = bm.get(metric, {}).get("high", 0)
                if target and bm_high and target > bm_high * 2:
                    issues.append(
                        f"{stage}/{metric}: target {target} > 2x "
                        f"industry high ({bm_high})"
                    )
        return {"valid": len(issues) == 0, "issues": issues}

    def check_test_sample_size(
        self, test_plan: dict[str, Any], budget: float
    ) -> dict[str, Any]:
        """PG-09: Test sample sizes must be achievable within budget."""
        issues = []
        for test in test_plan.get("tests", []):
            sample = test.get("sample_size_per_variant", 0)
            variants = len(test.get("variants", []))
            if sample < 100 and variants > 0:
                issues.append(
                    f"Test '{test.get('variable', '')}': "
                    f"sample size {sample} too small (min 100)"
                )
        return {"valid": len(issues) == 0, "issues": issues}

    def check_placement_objective_compat(
        self, ad_sets: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """PG-10: Placement must be compatible with objective."""
        issues = []
        for ad_set in ad_sets:
            objective = ad_set.get("objective", "")
            placements = set(ad_set.get("placements", []))
            allowed = _PLACEMENT_RESTRICTIONS.get(objective)
            if allowed:
                invalid = placements - allowed
                if invalid:
                    issues.append(
                        f"Ad set '{ad_set.get('name', '')}': "
                        f"placements {invalid} incompatible with "
                        f"{objective}"
                    )
        return {"valid": len(issues) == 0, "issues": issues}


class OutputGuardrails:
    """Validate the final blueprint output."""

    def check_meta_api_schema(self, blueprint: dict[str, Any]) -> dict[str, Any]:
        """OG-06: Validate blueprint against Meta API requirements."""
        issues = []

        # Campaign objective
        objective = blueprint.get("campaign_objective", "")
        if objective and objective not in _VALID_OBJECTIVES:
            issues.append(
                f"Invalid campaign objective: {objective}. "
                f"Valid: {_VALID_OBJECTIVES}"
            )

        # Ad sets
        ad_sets = blueprint.get("ad_sets", [])
        if not ad_sets:
            issues.append("Blueprint has no ad sets")

        for ad_set in ad_sets:
            obj = ad_set.get("objective", "")
            if obj and obj not in _VALID_OBJECTIVES:
                issues.append(
                    f"Ad set '{ad_set.get('name', '')}' has "
                    f"invalid objective: {obj}"
                )
            if not ad_set.get("targeting"):
                issues.append(f"Ad set '{ad_set.get('name', '')}' has no targeting")
            if not ad_set.get("placements"):
                issues.append(f"Ad set '{ad_set.get('name', '')}' has no placements")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "meta_api_compatible": len(issues) == 0,
        }

    def check_budget_cap(self, blueprint: dict[str, Any]) -> dict[str, Any]:
        """OG-08: Total ad set budgets must not exceed campaign budget."""
        campaign_budget = blueprint.get("daily_budget", 0)
        ad_set_total = sum(
            a.get("daily_budget", 0) for a in blueprint.get("ad_sets", [])
        )

        if campaign_budget > 0 and ad_set_total > 0:
            diff_pct = abs(ad_set_total - campaign_budget) / campaign_budget * 100
            if diff_pct > 1.0:
                return {
                    "valid": False,
                    "issue": (
                        f"Ad set budgets (${ad_set_total:.2f}) differ from "
                        f"campaign budget (${campaign_budget:.2f}) "
                        f"by {diff_pct:.1f}%"
                    ),
                }
        return {"valid": True}
