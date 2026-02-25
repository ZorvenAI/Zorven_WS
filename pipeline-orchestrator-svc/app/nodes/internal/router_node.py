"""
RouterNode — Intent routing for auto-detect mode.

When a job is submitted without an explicit manifest, the RouterNode
uses keyword matching on the input_prompt to select the best pipeline
from available_manifests.

Keywords carry different weights — platform names (linkedin, twitter)
score higher than generic verbs (write, blog) so that "write a blog
and post it in LinkedIn" routes to social-promotion, not blog-authoring.
"""

from app.nodes.base import BaseNode
from app.state.schema import AgentState

# Weighted keyword map: each entry is (keyword, weight).
# Higher weight = stronger signal for that pipeline.
KEYWORD_MAP: dict[str, list[tuple[str, int]]] = {
    "social-promotion": [
        # Platform names — strong signal (weight 3)
        ("linkedin", 3),
        ("twitter", 3),
        ("facebook", 3),
        ("instagram", 3),
        # Phrases (weight 2)
        ("post to linkedin", 2),
        ("post in linkedin", 2),
        ("post on linkedin", 2),
        ("post it in linkedin", 2),
        ("post it on linkedin", 2),
        ("post it to linkedin", 2),
        ("post to twitter", 2),
        ("post on twitter", 2),
        ("share on", 2),
        ("share in", 2),
        ("promote on", 2),
        ("tweet about", 2),
        ("tweet", 2),
        ("linkedin post", 2),
        ("facebook post", 2),
        ("schedule post", 2),
        ("scheduled task", 2),
        ("schedule it", 2),
        # Generic (weight 1)
        ("social", 1),
        ("promote", 1),
        ("social media", 1),
        ("schedule", 1),
        ("scheduled", 1),
    ],
    "social-post": [
        ("post on", 1),
        ("schedule post", 1),
        ("publish to", 1),
    ],
    "blog-authoring": [
        ("blog", 1),
        ("write", 1),
        ("author", 1),
        ("article", 1),
        ("publish", 1),
    ],
    "iso-brand-equity": [
        ("brand equity", 1),
        ("valuation", 1),
        ("iso", 1),
        ("royalty", 1),
        ("10668", 1),
    ],
    "competitor-audit": [
        ("competitor", 1),
        ("audit", 1),
        ("gap", 1),
        ("competitive", 1),
    ],
    "content-strategy": [
        ("content", 1),
        ("strategy", 1),
        ("calendar", 1),
        ("editorial", 1),
    ],
    "brand-analysis": [
        ("brand", 1),
        ("analysis", 1),
        ("positioning", 1),
        ("market", 1),
    ],
    "general-chat": [
        ("document", 1),
        ("file", 1),
        ("upload", 1),
        ("pdf", 1),
        ("summary", 1),
        ("summarize", 1),
        ("what does", 1),
        ("explain", 1),
        ("tell me about", 1),
        ("find", 1),
        ("search", 1),
        ("look up", 1),
    ],
}


class RouterNode(BaseNode):
    """Routes to the appropriate pipeline via weighted keyword matching."""

    async def __call__(self, state: AgentState) -> dict:
        prompt = state.get("input_prompt", "").lower()
        available = state.get("available_manifests") or []

        available_ids = {m["pipeline_id"] for m in available} if available else set()

        resolved_id = "brand-analysis"  # default fallback
        best_score = 0

        for pipeline_id, keywords in KEYWORD_MAP.items():
            if available_ids and pipeline_id not in available_ids:
                continue
            score = sum(weight for kw, weight in keywords if kw in prompt)
            if score > best_score:
                best_score = score
                resolved_id = pipeline_id

        return {"resolved_manifest_id": resolved_id}
