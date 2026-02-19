"""ReportNode — Report generation stub."""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class ReportNode(BaseNode):
    """Generates a formatted report from previous outputs (stub)."""

    async def __call__(self, state: AgentState) -> dict:
        node_outputs = dict(state.get("node_outputs", {}))
        previous = {k: v for k, v in node_outputs.items() if k != "report_generator"}

        node_outputs["report_generator"] = {
            "format": "markdown",
            "sections": list(previous.keys()),
            "findings": [
                "Comprehensive analysis across all pipeline stages.",
                "Data-driven insights gathered from multiple sources.",
            ],
            "recommendations": [
                "Implement findings within the next quarter.",
                "Schedule follow-up analysis in 90 days.",
            ],
        }
        return {"node_outputs": node_outputs}
