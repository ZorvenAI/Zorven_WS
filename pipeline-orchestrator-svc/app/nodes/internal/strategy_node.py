"""StrategyNode — Brand strategy analysis stub."""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class StrategyNode(BaseNode):
    """Produces brand strategy analysis (stub)."""

    async def __call__(self, state: AgentState) -> dict:
        prompt = state.get("input_prompt", "")
        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["brand_strategist"] = {
            "strategy_type": "differentiation",
            "target_segments": ["tech-savvy professionals", "early adopters"],
            "brand_positioning": f"Premium quality solution based on: {prompt[:100]}",
            "findings": [
                "Brand has strong recognition in target segments.",
                "Market positioning aligns with premium strategy.",
            ],
            "recommendations": [
                "Focus messaging on unique value proposition.",
                "Expand into adjacent market segments.",
            ],
        }
        return {"node_outputs": node_outputs}
