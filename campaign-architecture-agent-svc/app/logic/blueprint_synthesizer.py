"""SKL-CAA-10: Blueprint Synthesizer.

Builds the capstone system prompt for Claude call 2: assemble the full
CampaignBlueprint JSON from call 1 results + A/B test plan.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class BlueprintSynthesizer:
    """Build capstone blueprint synthesis system prompt."""

    def build_system_prompt(self) -> str:
        """Build the system prompt for Claude call 2 (blueprint assembly)."""
        return (
            "You are a Meta Ads campaign architect with deep expertise in "
            "the Meta Marketing API. Your task is to assemble a complete, "
            "production-ready CampaignBlueprint JSON.\n\n"
            "Requirements:\n"
            "1. The blueprint must be Meta Marketing API-compatible\n"
            "2. Campaign objectives must use valid Meta API enum values: "
            "AWARENESS, TRAFFIC, ENGAGEMENT, LEADS, APP_PROMOTION, SALES\n"
            "3. Budget allocations across ad sets must sum to the campaign "
            "daily budget (±1%)\n"
            "4. Each ad set must have targeting, placements, and budget\n"
            "5. Include risk assessment and performance projections\n"
            "6. Generate creative briefs for each audience × funnel combo\n\n"
            "Output format: A single JSON object with these top-level keys:\n"
            "- blueprint: {campaign_name, campaign_objective, "
            "special_ad_category, buying_type, daily_budget, bid_strategy, "
            "cbo_enabled, ad_sets: [{name, funnel_stage, objective, "
            "targeting, placements, daily_budget, bid_strategy, "
            "optimization_goal, creative_briefs}]}\n"
            "- funnel_map: {stages: [{stage, meta_objective, budget_pct, "
            "description}]}\n"
            "- targeting_specs: [{ad_set_name, funnel_stage, demographics, "
            "interests, behaviors, custom_audiences, "
            "lookalike_audiences, exclusions, "
            "estimated_audience_size}]\n"
            "- placement_budget: {cbo_enabled, bid_strategy, "
            "per_ad_set: [{ad_set_name, placements, daily_budget, "
            "optimization_goal}]}\n"
            "- test_plan: {tests, total_testing_budget_pct, "
            "total_variants}\n"
            "- kpi_targets: {per_funnel: {stage: {cpm, ctr, cpc, cpa, "
            "roas}}}\n"
            "- performance_projections: {estimated_reach, "
            "estimated_impressions, estimated_clicks, "
            "estimated_conversions, projected_roas, "
            "confidence_range}\n"
            "- risk_assessment: {risks: [{category, description, "
            "severity, mitigation}]}\n"
            "- creative_briefs: [{ad_set_name, format, headline, "
            "primary_text, cta, visual_direction}]\n"
            "- confidence_score: float (0-1)\n\n"
            "Return ONLY valid JSON, no markdown or commentary."
        )

    def build_user_prompt(
        self,
        call1_result: dict[str, Any],
        test_plan_section: str,
        benchmark_section: str,
        competitor_section: str,
        budget: float,
        company_name: str = "",
    ) -> str:
        """Build user prompt for Claude call 2 with call 1 results."""
        prompt = f"# Campaign Blueprint for {company_name}\n\n"
        prompt += f"Daily budget: ${budget:.2f}\n\n"

        prompt += "## Architecture Synthesis Results (from analysis)\n\n"
        prompt += f"```json\n{json.dumps(call1_result, indent=2)}\n```\n\n"

        prompt += test_plan_section + "\n"
        prompt += benchmark_section + "\n"
        prompt += competitor_section + "\n"

        prompt += (
            "\nAssemble the complete CampaignBlueprint JSON "
            "incorporating all the above analysis."
        )

        return prompt
