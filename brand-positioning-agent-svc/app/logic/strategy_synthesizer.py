"""SKL-BPA-10: Strategy Synthesizer.

Assembles the capstone strategy document: executive summary,
recommended positioning, UVP, canvas, maps, differentiation,
implementation guidelines, risk assessment.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StrategySynthesizer:
    """Assembles full positioning strategy document."""

    async def synthesize(
        self,
        recommended: dict[str, Any],
        alternatives: list[dict[str, Any]],
        canvas: dict[str, Any],
        maps: list[dict[str, Any]],
        differentiation: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Assemble the complete positioning strategy.

        Returns:
            Full strategy document dict.
        """
        return {
            "executive_summary": self._build_executive_summary(
                recommended, differentiation
            ),
            "recommended_positioning": recommended,
            "alternative_positions": alternatives,
            "value_proposition_canvas": canvas,
            "perceptual_maps": maps,
            "differentiation_framework": differentiation,
            "implementation_guidelines": self._build_guidelines(recommended),
            "risk_assessment": self._build_risk_assessment(
                recommended, differentiation
            ),
            "wf1_data_summary": {
                "mra_available": bool(context.get("mra")),
                "cia_available": bool(context.get("cia")),
                "apa_available": bool(context.get("apa")),
                "tcia_available": bool(context.get("tcia")),
                "voca_available": bool(context.get("voca")),
            },
        }

    def _build_executive_summary(
        self,
        recommended: dict[str, Any],
        differentiation: dict[str, Any],
    ) -> str:
        """Build executive summary from recommended positioning."""
        statement = recommended.get("statement", "")
        framework = recommended.get("framework_used", "")
        diff_score = differentiation.get("overall_differentiation_score", 0)
        pods_count = len(differentiation.get("pods", []))

        if not statement:
            return "Positioning strategy pending analysis."

        return (
            f"Recommended positioning using {framework} framework. "
            f"Differentiation score: {diff_score}/100 with "
            f"{pods_count} points of difference identified."
        )

    def _build_guidelines(self, recommended: dict[str, Any]) -> list[str]:
        """Build implementation guidelines."""
        guidelines = [
            "Align all brand communications with the positioning statement",
            "Update brand messaging hierarchy across all channels",
            "Train customer-facing teams on positioning rationale",
            "Monitor competitive response and adjust as needed",
            "Conduct quarterly positioning health checks",
        ]
        return guidelines

    def _build_risk_assessment(
        self,
        recommended: dict[str, Any],
        differentiation: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build risk assessment for the positioning strategy."""
        risks = []
        scores = recommended.get("scores", {})

        if scores.get("differentiation", 100) < 60:
            risks.append(
                {
                    "risk": "Low differentiation score",
                    "severity": "high",
                    "mitigation": (
                        "Strengthen unique value proposition "
                        "with additional proof points"
                    ),
                }
            )

        if scores.get("believability", 100) < 60:
            risks.append(
                {
                    "risk": "Low believability score",
                    "severity": "medium",
                    "mitigation": (
                        "Gather more evidence and testimonials "
                        "to support positioning claims"
                    ),
                }
            )

        return risks
