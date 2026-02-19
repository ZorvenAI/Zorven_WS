"""AudienceNode — Audience analysis stub."""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class AudienceNode(BaseNode):
    """Produces audience demographics and psychographics (stub)."""

    async def __call__(self, state: AgentState) -> dict:
        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["audience_analyzer"] = {
            "primary_audience": {
                "age_range": "25-45",
                "interests": ["technology", "innovation", "business"],
                "platforms": ["LinkedIn", "Twitter", "YouTube"],
            },
            "secondary_audience": {
                "age_range": "18-30",
                "interests": ["social media", "trends", "lifestyle"],
                "platforms": ["Instagram", "TikTok"],
            },
            "findings": [
                "Primary audience is active on professional networks.",
                "Secondary audience prefers visual content platforms.",
            ],
            "recommendations": [
                "Create platform-specific content strategies.",
                "Leverage LinkedIn for B2B engagement.",
            ],
        }
        return {"node_outputs": node_outputs}
