"""Context variable registry (§7.5.5).

Defines all valid {context.*} placeholder variables that prompt
templates may reference. GEPA optimizes only the instruction layer;
{context.*} placeholders are filled at runtime with tenant data.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ContextVariable:
    """A registered context variable."""

    name: str
    type: str = "str"
    source: str = "onboarding"  # onboarding | runtime | upstream
    required: bool = False
    description: str = ""
    agents: Optional[tuple[str, ...]] = None  # None = all agents


# Shared across all agents (onboarding data)
SHARED_VARIABLES = [
    ContextVariable(
        "context.brand_name", source="onboarding", required=True,
        description="Company/brand name from onboarding",
    ),
    ContextVariable(
        "context.industry", source="onboarding", required=True,
        description="Industry classification from onboarding",
    ),
    ContextVariable(
        "context.target_audience", source="onboarding",
        description="Target audience description from onboarding",
    ),
    ContextVariable(
        "context.brand_voice", source="onboarding",
        description="Brand voice/tone from onboarding",
    ),
    ContextVariable(
        "context.product_description", source="onboarding",
        description="Product/service description from onboarding",
    ),
]

# WF1 agent-specific variables
WF1_VARIABLES = [
    ContextVariable(
        "context.query", source="runtime", required=True,
        description="User's research query",
        agents=("mra", "cia", "apa", "tcia", "voca"),
    ),
    ContextVariable(
        "context.competitors", source="runtime",
        description="Known competitors list",
        agents=("cia",),
    ),
    ContextVariable(
        "context.audience_data", source="runtime",
        description="Audience data for segmentation",
        agents=("apa",),
    ),
    ContextVariable(
        "context.trends", source="runtime",
        description="Trends to score for brand relevance",
        agents=("tcia",),
    ),
    ContextVariable(
        "context.feedback_data", source="runtime",
        description="Customer feedback for VoC analysis",
        agents=("voca",),
    ),
    ContextVariable(
        "context.raw_findings", source="upstream",
        description="Raw research findings for synthesis",
        agents=("mra",),
    ),
]

# WF2 agent-specific variables
WF2_VARIABLES = [
    ContextVariable(
        "context.market_research", source="upstream",
        description="MRA output for positioning context",
        agents=("bpa", "baa", "bpv", "nta", "bsa"),
    ),
    ContextVariable(
        "context.positioning", source="upstream",
        description="BPA positioning output",
        agents=("baa", "bpv", "nta", "bsa"),
    ),
    ContextVariable(
        "context.personality", source="upstream",
        description="BPV personality output",
        agents=("nta", "bsa"),
    ),
    ContextVariable(
        "context.voice", source="upstream",
        description="BPV voice matrix output",
        agents=("nta", "bsa"),
    ),
    ContextVariable(
        "context.portfolio", source="upstream",
        description="Current brand portfolio",
        agents=("baa",),
    ),
    ContextVariable(
        "context.architecture", source="upstream",
        description="BAA architecture output",
        agents=("baa",),
    ),
    ContextVariable(
        "context.values", source="upstream",
        description="Brand values from BPV",
        agents=("bsa",),
    ),
    ContextVariable(
        "context.brand_story", source="upstream",
        description="Brand story context",
        agents=("bsa",),
    ),
    ContextVariable(
        "context.founder_info", source="onboarding",
        description="Founder context for origin story",
        agents=("bsa",),
    ),
]

# WF3 agent-specific variables
WF3_VARIABLES = [
    ContextVariable(
        "context.objective", source="runtime",
        description="Campaign objective",
        agents=("caa",),
    ),
    ContextVariable(
        "context.budget", source="runtime",
        description="Campaign budget",
        agents=("caa", "coa"),
    ),
    ContextVariable(
        "context.personas", source="upstream",
        description="Audience personas from APA",
        agents=("caa",),
    ),
    ContextVariable(
        "context.campaign_blueprint", source="upstream",
        description="CAA campaign architecture output",
        agents=("cga", "adpub"),
    ),
    ContextVariable(
        "context.creative_profiles", source="upstream",
        description="CGA creative profiles output",
        agents=("cga",),
    ),
    ContextVariable(
        "context.ad_units", source="upstream",
        description="CGA ad units for compliance review",
        agents=("cga",),
    ),
    ContextVariable(
        "context.creative_packages", source="upstream",
        description="CGA creative packages for publishing",
        agents=("adpub",),
    ),
    ContextVariable(
        "context.campaign_name", source="upstream",
        description="Campaign name for approval summary",
        agents=("adpub",),
    ),
    ContextVariable(
        "context.ad_set_count", source="upstream",
        description="Number of ad sets",
        agents=("adpub",),
    ),
    ContextVariable(
        "context.creative_count", source="upstream",
        description="Number of creatives",
        agents=("adpub",),
    ),
    ContextVariable(
        "context.campaign_metrics", source="upstream",
        description="Campaign performance metrics",
        agents=("coa",),
    ),
    ContextVariable(
        "context.performance_data", source="upstream",
        description="Performance data for recommendations",
        agents=("coa",),
    ),
    ContextVariable(
        "context.guardrails", source="runtime",
        description="Optimization guardrails config",
        agents=("coa",),
    ),
    ContextVariable(
        "context.campaign_state", source="upstream",
        description="Current campaign state for planner",
        agents=("coa",),
    ),
    ContextVariable(
        "context.budget_remaining", source="upstream",
        description="Remaining budget for planner",
        agents=("coa",),
    ),
    ContextVariable(
        "context.optimization_data", source="upstream",
        description="Optimization data for learning extraction",
        agents=("ila",),
    ),
    ContextVariable(
        "context.learning_history", source="upstream",
        description="Historical learnings for synthesis",
        agents=("ila",),
    ),
    ContextVariable(
        "context.recent_actions", source="upstream",
        description="Recent optimization actions for planner",
        agents=("ila",),
    ),
]

# Complete registry
CONTEXT_REGISTRY: dict[str, ContextVariable] = {}
for var in SHARED_VARIABLES + WF1_VARIABLES + WF2_VARIABLES + WF3_VARIABLES:
    CONTEXT_REGISTRY[var.name] = var

# All valid placeholder names
VALID_PLACEHOLDER_NAMES: set[str] = set(CONTEXT_REGISTRY.keys())
