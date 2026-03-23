"""SKL-BPA-06: Positioning Statement Generator.

Generates N positioning candidates across multiple frameworks:
classic, blue_ocean, jtbd, category_creation, challenger.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

FRAMEWORKS = [
    "classic",
    "blue_ocean",
    "jtbd",
    "category_creation",
    "challenger",
]


class PositioningGenerator:
    """Generates framework-agnostic positioning statements."""

    async def generate(
        self,
        context: dict[str, Any],
        candidate_count: int = 3,
    ) -> list[dict[str, Any]]:
        """Generate positioning candidates.

        This method prepares context for the LLM to generate
        framework-diverse positioning statements. Actual generation
        happens in BPAAnalyzer via Claude.

        Returns:
            List of positioning candidate dicts.
        """
        # Determine which frameworks to use based on context
        frameworks_to_use = self._select_frameworks(context, candidate_count)
        return [
            {"framework": fw, "context_summary": self._summarize(context)}
            for fw in frameworks_to_use
        ]

    def _select_frameworks(self, context: dict[str, Any], count: int) -> list[str]:
        """Select frameworks based on available context."""
        # Always include classic; distribute others based on count
        selected = ["classic"]
        remaining = [f for f in FRAMEWORKS if f != "classic"]
        for fw in remaining[: count - 1]:
            selected.append(fw)
        return selected[:count]

    def _summarize(self, context: dict[str, Any]) -> str:
        """Create brief context summary for positioning."""
        parts = []
        if context.get("mra"):
            parts.append("Market research available")
        if context.get("cia"):
            parts.append("Competitive intelligence available")
        if context.get("apa"):
            parts.append("Audience personas available")
        if context.get("tcia"):
            parts.append("Trend analysis available")
        if context.get("voca"):
            parts.append("VoC analysis available")
        return "; ".join(parts) if parts else "Limited context"
