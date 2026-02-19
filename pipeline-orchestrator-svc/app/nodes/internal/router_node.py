"""
RouterNode — Intent routing for auto-detect mode.

When a job is submitted without an explicit manifest, the RouterNode
uses keyword matching on the input_prompt to select the best pipeline
from available_manifests.
"""

from app.nodes.base import BaseNode
from app.state.schema import AgentState

KEYWORD_MAP: dict[str, list[str]] = {
    "iso-brand-equity": ["brand equity", "valuation", "iso", "royalty", "10668"],
    "competitor-audit": ["competitor", "audit", "gap", "competitive"],
    "content-strategy": ["content", "strategy", "calendar", "editorial"],
    "brand-analysis": ["brand", "analysis", "positioning", "market"],
}


class RouterNode(BaseNode):
    """Routes to the appropriate pipeline via keyword matching."""

    async def __call__(self, state: AgentState) -> dict:
        prompt = state.get("input_prompt", "").lower()
        available = state.get("available_manifests") or []

        available_ids = {m["pipeline_id"] for m in available} if available else set()

        resolved_id = "brand-analysis"  # default fallback
        best_score = 0

        for pipeline_id, keywords in KEYWORD_MAP.items():
            if available_ids and pipeline_id not in available_ids:
                continue
            score = sum(1 for kw in keywords if kw in prompt)
            if score > best_score:
                best_score = score
                resolved_id = pipeline_id

        return {"resolved_manifest_id": resolved_id}
