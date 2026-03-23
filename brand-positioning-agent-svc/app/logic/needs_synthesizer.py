"""SKL-BPA-02: Audience Needs Synthesizer.

Synthesizes APA personas + VoCA themes into a needs hierarchy:
table-stakes, differentiators, delighters.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NeedsSynthesizer:
    """Synthesizes audience needs from APA + VoCA data."""

    async def synthesize(
        self,
        apa_data: dict[str, Any],
        voca_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Build needs hierarchy from persona and VoC data.

        Returns:
            Needs hierarchy with table-stakes, differentiators, delighters.
        """
        personas = apa_data.get("personas", [])
        pain_matrix = voca_data.get("pain_point_priority_matrix", {})
        pain_points = pain_matrix.get("pain_points", [])
        themes = voca_data.get("themes", {}).get("themes", [])

        # Categorize needs by severity/frequency
        table_stakes = []
        differentiators = []
        delighters = []

        for pp in pain_points:
            severity = pp.get("severity", 0)
            if isinstance(pp, dict):
                need = {
                    "name": pp.get("name", ""),
                    "severity": severity,
                    "personas_impacted": pp.get("persona_impact", []),
                    "source": "voc_pain_point",
                }
                if severity >= 8:
                    table_stakes.append(need)
                elif severity >= 5:
                    differentiators.append(need)
                else:
                    delighters.append(need)

        return {
            "table_stakes": table_stakes,
            "differentiators": differentiators,
            "delighters": delighters,
            "personas_analyzed": len(personas),
            "pain_points_analyzed": len(pain_points),
            "themes_analyzed": len(themes),
            "persona_summaries": [
                {
                    "slug": p.get("slug", ""),
                    "label": p.get("segment_label", ""),
                    "pain_points": p.get("pain_points", []),
                }
                for p in personas[:5]
                if isinstance(p, dict)
            ],
        }
