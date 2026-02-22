"""
Proxy Engine — dynamic weight redistribution for missing data.

When the full ISO 10668 data set is unavailable (e.g., no financial
statements), this engine redistributes pillar weights so that
available data pillars absorb the missing pillar's weight
proportionally.

Example: If Financials (40%) is missing:
  - Behavioral: 35% / (35% + 25%) = 58.3%
  - Legal: 25% / (35% + 25%) = 41.7%
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ProxyEngine:
    """Dynamic weight redistribution when data is incomplete."""

    def get_calculation_strategy(self, data_manifest: dict[str, Any]) -> str:
        """
        Determine calculation mode based on data availability.

        Returns:
            "STANDARD_ROYALTY_RELIEF" — full financial data available
            "PRICE_PREMIUM_MODE" — no financial data, use price premium proxy
        """
        if not data_manifest.get("financial_data"):
            logger.info("No financial data — switching to PRICE_PREMIUM_MODE")
            return "PRICE_PREMIUM_MODE"
        return "STANDARD_ROYALTY_RELIEF"

    def redistribute_weights(
        self,
        available_pillars: list[str],
        default_weights: dict[str, float],
    ) -> dict[str, float]:
        """
        Normalize weights across available pillars only.

        Each available pillar's weight is scaled proportionally so the
        total sums to 1.0.

        Args:
            available_pillars: List of pillar names with data.
            default_weights: Standard pillar weights (e.g., {financial: 0.40, ...}).

        Returns:
            Redistributed weights dict summing to 1.0.
        """
        if not available_pillars:
            logger.warning("No pillars available for weight redistribution")
            return {}

        available_weights = {
            k: v for k, v in default_weights.items() if k in available_pillars
        }
        total = sum(available_weights.values())

        if total == 0:
            # Equal distribution as fallback
            equal_weight = 1.0 / len(available_pillars)
            return {p: equal_weight for p in available_pillars}

        redistributed = {k: v / total for k, v in available_weights.items()}

        logger.debug(
            "Weight redistribution: %s → %s (pillars: %s)",
            {k: f"{v:.1%}" for k, v in default_weights.items()},
            {k: f"{v:.1%}" for k, v in redistributed.items()},
            available_pillars,
        )

        return redistributed

    def assess_data_completeness(
        self,
        financial_data: Any | None,
        behavioral_data: Any | None,
        legal_data: Any | None,
    ) -> float:
        """
        Calculate data completeness fraction (0.0–1.0).

        Returns the fraction of ISO pillars with available data.
        """
        total = 3
        available = sum(
            1 for d in [financial_data, behavioral_data, legal_data] if d is not None
        )
        return available / total
