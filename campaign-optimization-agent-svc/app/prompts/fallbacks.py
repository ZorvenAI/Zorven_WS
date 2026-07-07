"""Fallback prompts for COA — CRITICAL agent (manages ad spend).

AC-2: Fallback triggers HIGH-severity warning.
"""

CRITICAL_AGENT = True  # AC-2: HIGH-severity warning on fallback

FALLBACK_SYSTEM = (
    "You are a Meta Ads optimization specialist. Analyze campaign "
    "performance, generate optimization recommendations, and manage "
    "spend guardrails. Follow PG-01 planner-guided decision framework."
)
FALLBACK_OPTIMIZATION = (
    "Analyze Meta Ads performance. Identify underperforming ad sets, "
    "creative fatigue, and budget reallocation opportunities. Respond "
    "with valid JSON."
)
FALLBACK_RECOMMENDATION = (
    "Generate actionable optimization recommendations. Prioritize by "
    "impact and rank kill/scale/test actions. Respond with valid JSON."
)
FALLBACK_MAP = {
    "zorven-wf3-coa-system": FALLBACK_SYSTEM,
    "zorven-wf3-coa-optimization": FALLBACK_OPTIMIZATION,
    "zorven-wf3-coa-recommendation": FALLBACK_RECOMMENDATION,
}
