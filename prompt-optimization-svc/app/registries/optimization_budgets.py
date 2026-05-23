"""Per-agent GEPA optimization budgets (§4.3).

max_metric_calls controls the total number of scorer evaluations
GEPA may perform during an optimization run. Higher budgets allow
more exploration but cost more in LLM calls.
"""

# Per-agent max_metric_calls defaults
AGENT_BUDGETS: dict[str, int] = {
    # WF3 — highest ROI agents
    "cga": 500,   # Creative Generation — complex multi-output
    "caa": 400,   # Campaign Architecture — structural complexity
    "adpub": 300, # Ad Publishing — CRITICAL (ad spend)
    "coa": 300,   # Campaign Optimization — CRITICAL (ad spend)
    "ila": 250,   # Intelligence Loop — cross-campaign synthesis
    # WF2 — brand strategy agents
    "bpa": 300,   # Brand Positioning — high strategic impact
    "bpv": 250,   # Brand Personality — values/voice matrix
    "baa": 250,   # Brand Architecture — hierarchy complexity
    "nta": 250,   # Brand Naming — creative generation
    "bsa": 250,   # Brand Story — narrative quality
    # WF1 — discovery/research agents
    "mra": 200,   # Market Research — structured output
    "cia": 200,   # Competitor Intelligence — analysis quality
    "apa": 200,   # Audience Persona — profiling depth
    "tcia": 200,  # Trend Cultural — scoring accuracy
    "voca": 200,  # Voice of Customer — sentiment precision
}

DEFAULT_BUDGET = 200


def get_budget(agent_code: str) -> int:
    """Get the max_metric_calls budget for an agent."""
    return AGENT_BUDGETS.get(agent_code.lower(), DEFAULT_BUDGET)
