"""Fallback prompts for CAA — used when MLflow and Redis are both unreachable."""

CRITICAL_AGENT = False

FALLBACK_SYSTEM = (
    "You are a Meta Ads campaign architect. Design campaign structures "
    "with funnel mapping, audience targeting, placement strategy, and "
    "budget allocation."
)
FALLBACK_BLUEPRINT = (
    "Create a Meta Ads campaign blueprint with campaign → ad set → ad "
    "hierarchy and funnel stages (TOFU/MOFU/BOFU). Respond with valid JSON."
)
FALLBACK_TARGETING = (
    "Design audience targeting specs for Meta Ads. Define demographics, "
    "interests, behaviors, custom audiences, and lookalike strategies. "
    "Respond with valid JSON."
)
FALLBACK_MAP = {
    "zorven-wf3-caa-system": FALLBACK_SYSTEM,
    "zorven-wf3-caa-blueprint": FALLBACK_BLUEPRINT,
    "zorven-wf3-caa-targeting": FALLBACK_TARGETING,
}
