"""CalendarNode — Editorial calendar stub."""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class CalendarNode(BaseNode):
    """Produces an editorial calendar with scheduled content (stub)."""

    async def __call__(self, state: AgentState) -> dict:
        node_outputs = dict(state.get("node_outputs", {}))
        node_outputs["calendar_builder"] = {
            "schedule": [
                {
                    "week": 1,
                    "monday": "Blog: Industry Trends",
                    "wednesday": "Social: Tips Thread",
                    "friday": "Video: Product Demo",
                },
                {
                    "week": 2,
                    "monday": "Blog: Case Study",
                    "wednesday": "Social: Behind the Scenes",
                    "friday": "Infographic: Stats",
                },
                {
                    "week": 3,
                    "monday": "Blog: Thought Leadership",
                    "wednesday": "Social: Poll/Q&A",
                    "friday": "Video: Interview",
                },
                {
                    "week": 4,
                    "monday": "Blog: How-To Guide",
                    "wednesday": "Social: User Spotlight",
                    "friday": "Newsletter: Monthly Recap",
                },
            ],
            "findings": [
                "Consistent posting schedule improves audience retention.",
                "Monday and Wednesday are optimal publishing days.",
            ],
            "recommendations": [
                "Maintain the 3x/week cadence for 90 days.",
                "Review performance metrics bi-weekly.",
            ],
        }
        return {"node_outputs": node_outputs}
