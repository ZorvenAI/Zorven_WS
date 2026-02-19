"""PlannerNode — Content planning stub."""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class PlannerNode(BaseNode):
    """Produces content plans with themes and topics (stub)."""

    async def __call__(self, state: AgentState) -> dict:
        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["content_planner"] = {
            "themes": [
                "Thought Leadership",
                "Product Innovation",
                "Customer Success Stories",
            ],
            "content_types": ["blog_posts", "social_media", "video", "infographic"],
            "frequency": "3x per week",
            "findings": [
                "Content gaps exist in thought leadership category.",
                "Video content shows highest engagement rates.",
            ],
            "recommendations": [
                "Increase thought leadership content output.",
                "Invest in short-form video production.",
            ],
        }
        return {"node_outputs": node_outputs}
