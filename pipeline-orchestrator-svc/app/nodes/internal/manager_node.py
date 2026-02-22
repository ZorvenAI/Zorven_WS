"""
ManagerNode — Aggregates node outputs into final result_data.

This is typically the terminal node in a pipeline. It collects
all previous node outputs and formats them for the frontend
ResultDashboard and BrandEquityDashboard components.
"""

from typing import Any

from app.nodes.base import BaseNode
from app.state.schema import AgentState


class ManagerNode(BaseNode):
    """Aggregates all node outputs into a structured result."""

    async def __call__(self, state: AgentState) -> dict:
        outputs = state.get("node_outputs", {})

        findings: list[str] = []
        recommendations: list[str] = []

        for node_id, output in outputs.items():
            if isinstance(output, dict):
                findings.extend(output.get("findings", []))
                recommendations.extend(output.get("recommendations", []))

        # Extract BSI and valuation data from intelligence agent output
        bsi_data = self._extract_bsi(outputs)
        valuation_data = self._extract_valuation(outputs)

        result_data: dict[str, Any] = {
            "summary": (
                f"Pipeline analysis completed. "
                f"Processed {len(outputs)} agent(s) with results."
            ),
            "findings": findings or ["Analysis completed successfully."],
            "recommendations": recommendations
            or ["Review the detailed node outputs for actionable insights."],
            "node_results": outputs,
        }

        # Populate score from BSI (used by BrandEquityDashboard)
        if bsi_data:
            result_data["score"] = bsi_data.get("score", 0)
            # Extract pillar scores for dashboard gauges
            pillars = bsi_data.get("pillars", [])
            for pillar in pillars:
                if isinstance(pillar, dict):
                    name = pillar.get("name", "").lower()
                    pillar_score = pillar.get("score")
                    if pillar_score is not None:
                        if "financial" in name:
                            result_data["financials"] = pillar_score
                        elif "behavioral" in name or "awareness" in name:
                            result_data["awareness"] = pillar_score
                        elif "legal" in name:
                            result_data["sentiment"] = pillar_score
        else:
            result_data["score"] = 0

        # Include valuation data if available
        if valuation_data:
            result_data["valuation"] = valuation_data

        return {"result_data": result_data}

    @staticmethod
    def _extract_bsi(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract BSI data from any node output."""
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                bsi = output.get("bsi")
                if isinstance(bsi, dict) and "score" in bsi:
                    return bsi
        return None

    @staticmethod
    def _extract_valuation(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract valuation data from any node output."""
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                val = output.get("valuation")
                if isinstance(val, dict) and "brand_value_npv" in val:
                    return val
        return None
