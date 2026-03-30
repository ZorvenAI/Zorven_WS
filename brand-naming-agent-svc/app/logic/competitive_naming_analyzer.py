"""SKL-NTA-03: Analyze competitor naming patterns, identify white space."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CompetitiveNamingAnalyzer:
    """Analyze competitor naming patterns to identify differentiation opportunities."""

    async def analyze(
        self,
        cia_data: dict[str, Any],
        mra_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract competitive naming landscape."""
        competitors = cia_data.get("competitors", [])
        market_context = mra_data.get("market_sizing", {})

        competitor_names = []
        naming_patterns = {
            "descriptive": [],
            "coined": [],
            "metaphorical": [],
            "acronym": [],
            "founder": [],
            "other": [],
        }

        for comp in competitors:
            name = comp.get("name", "")
            if name:
                competitor_names.append(name)
                pattern = self._classify_name(name)
                naming_patterns[pattern].append(name)

        # Identify white space — naming types least used by competitors
        white_space = []
        for ntype, names in naming_patterns.items():
            if len(names) <= 1:
                white_space.append(ntype)

        return {
            "competitor_names": competitor_names,
            "competitor_count": len(competitor_names),
            "naming_patterns": naming_patterns,
            "white_space_types": white_space,
            "market_context": market_context,
            "industry": mra_data.get("industry", ""),
        }

    def _classify_name(self, name: str) -> str:
        """Simple heuristic to classify a brand name type."""
        lower = name.lower()
        # Acronyms: all caps or very short
        if name.isupper() and len(name) <= 5:
            return "acronym"
        # Check for common descriptive patterns
        descriptive_hints = [
            "tech", "global", "solutions", "systems", "services",
            "digital", "smart", "pro", "data", "cloud",
        ]
        if any(hint in lower for hint in descriptive_hints):
            return "descriptive"
        # Names ending in common coined suffixes
        coined_suffixes = ["ify", "ly", "io", "oo", "ix", "fy"]
        if any(lower.endswith(s) for s in coined_suffixes):
            return "coined"
        return "other"
