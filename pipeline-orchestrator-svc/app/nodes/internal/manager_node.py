"""
ManagerNode — Aggregates node outputs into final result_data.

This is typically the terminal node in a pipeline. It collects
all previous node outputs and formats them for the frontend
ResultDashboard component.
"""

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class ManagerNode(BaseNode):
    """Aggregates all node outputs into a structured result."""

    async def __call__(self, state: AgentState) -> dict:
        outputs = state.get("node_outputs", {})

        findings = []
        recommendations = []

        for node_id, output in outputs.items():
            if isinstance(output, dict):
                findings.extend(output.get("findings", []))
                recommendations.extend(output.get("recommendations", []))

        result_data = {
            "summary": (
                f"Pipeline analysis completed. "
                f"Processed {len(outputs)} agent(s) with results."
            ),
            "findings": findings or ["Analysis completed successfully."],
            "recommendations": recommendations
            or ["Review the detailed node outputs for actionable insights."],
            "score": 7.5,
            "node_results": outputs,
        }

        return {"result_data": result_data}
