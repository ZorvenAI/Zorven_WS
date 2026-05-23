"""Fallback prompts for ILA — used when MLflow and Redis are both unreachable."""

CRITICAL_AGENT = False

FALLBACK_SYSTEM = (
    "You are a campaign intelligence analyst. Extract learnings from "
    "optimization actions, identify cross-campaign patterns, and feed "
    "insights back into the brand knowledge base."
)
FALLBACK_EXTRACTION = (
    "Extract campaign learnings: what worked, what failed, audience "
    "insights, creative insights, budget efficiency. Respond with valid JSON."
)
FALLBACK_SYNTHESIS = (
    "Synthesize campaign intelligence across optimization cycles. Generate "
    "patterns, recommendations, and RAG-ready knowledge entries. Respond "
    "with valid JSON."
)
FALLBACK_MAP = {
    "zorven-wf3-ila-system": FALLBACK_SYSTEM,
    "zorven-wf3-ila-extraction": FALLBACK_EXTRACTION,
    "zorven-wf3-ila-synthesis": FALLBACK_SYNTHESIS,
}
