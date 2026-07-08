"""Fallback prompts for COA — CRITICAL agent (manages ad spend).

These are verbatim copies of the system prompts currently used in production.
They serve as the last-resort fallback when both Redis cache and MLflow are
unavailable. The prompt-optimization-svc (MLflow) is the primary source of
truth; these fallbacks ensure zero-downtime degradation.

AC-2: Fallback triggers HIGH-severity warning (critical_agent=True).
"""

# Verbatim copy of system string from RecommendationGenerator._enrich_rationales()
# in recommendation_generator.py
FALLBACK_RECOMMENDATION = (
    "You are a Meta Ads optimization specialist. Generate a "
    "brief, actionable rationale (2-3 sentences) for each "
    "optimization action. Include the expected impact."
)

# Verbatim copy of system string from Reporter._generate_narrative()
# in reporter.py
FALLBACK_REPORTER = (
    "You are a Meta Ads performance analyst. Generate a concise "
    "performance report (4-6 sentences) covering: overall campaign "
    "health, key metrics vs typical benchmarks, top and bottom "
    "performing ad sets, trends, and recommended next steps."
)

# Map catalog names -> fallback constants for programmatic lookup
FALLBACK_MAP = {
    "zorven-wf3-coa-recommendation": FALLBACK_RECOMMENDATION,
    "zorven-wf3-coa-reporter": FALLBACK_REPORTER,
}
