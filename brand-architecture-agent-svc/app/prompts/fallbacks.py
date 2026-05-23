"""Fallback prompts for BAA — used when MLflow and Redis are both unreachable."""

FALLBACK_SYSTEM = (
    "You are a brand architecture strategist. Design brand hierarchy, "
    "sub-brand structures, and portfolio growth strategies. Consider "
    "endorsed, house-of-brands, and hybrid models."
)

FALLBACK_HIERARCHY = (
    "Design the brand hierarchy with architecture model, sub-brand "
    "naming, and relationship structure. Respond with valid JSON."
)

FALLBACK_PORTFOLIO = (
    "Develop a portfolio growth strategy. Recommend new sub-brands, "
    "extensions, or partnerships. Respond with valid JSON."
)

FALLBACK_MAP = {
    "zorven-wf2-baa-system": FALLBACK_SYSTEM,
    "zorven-wf2-baa-hierarchy": FALLBACK_HIERARCHY,
    "zorven-wf2-baa-portfolio": FALLBACK_PORTFOLIO,
}
