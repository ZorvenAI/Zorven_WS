"""SKL-BPA-09: Differentiation Builder.

Builds Points of Parity (POPs), Points of Difference (PODs),
Reasons to Believe (RTBs), positioning proof points, and
competitive vulnerability assessment.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class DifferentiationBuilder:
    """Builds differentiation framework from positioning analysis."""

    async def build(
        self,
        competitive_data: dict[str, Any],
        audience_needs: dict[str, Any],
        positioning: dict[str, Any],
    ) -> dict[str, Any]:
        """Build differentiation framework.

        Returns:
            Framework with POPs, PODs, RTBs, proof points, vulnerabilities.
        """
        return {
            "pops": self._identify_pops(competitive_data, audience_needs),
            "pods": self._identify_pods(competitive_data, audience_needs),
            "rtbs": [],
            "proof_points": [],
            "competitive_vulnerabilities": self._identify_vulnerabilities(
                competitive_data
            ),
            "overall_differentiation_score": 0.0,
        }

    def _identify_pops(
        self,
        competitive_data: dict[str, Any],
        audience_needs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Identify Points of Parity — table stakes the brand must match."""
        pops = []
        for need in audience_needs.get("table_stakes", []):
            if isinstance(need, dict):
                pops.append(
                    {
                        "attribute": need.get("name", ""),
                        "category": "table_stakes",
                        "importance": "high",
                    }
                )
        return pops

    def _identify_pods(
        self,
        competitive_data: dict[str, Any],
        audience_needs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Identify Points of Difference — unique differentiators."""
        pods = []
        gaps = competitive_data.get("positioning_gaps", [])
        for gap in gaps:
            if isinstance(gap, dict):
                pods.append(
                    {
                        "attribute": gap.get("dimension", ""),
                        "opportunity_score": gap.get("opportunity_score", 0),
                        "category": "competitive_gap",
                    }
                )
        return pods

    def _identify_vulnerabilities(
        self, competitive_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify competitive vulnerabilities to exploit."""
        vulnerabilities = []
        swot = competitive_data.get("swot_summary", {})
        if isinstance(swot, dict):
            for weakness in swot.get("weaknesses", []):
                vulnerabilities.append(
                    {
                        "competitor": "",
                        "vulnerability": weakness if isinstance(weakness, str) else "",
                        "exploitability": "medium",
                    }
                )
        return vulnerabilities
