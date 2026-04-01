"""SKL-CGA-03: Creative Learnings Loader.

Extracts creative performance learnings from previous pipeline outputs
to inform creative decisions. Returns empty learnings for first campaigns.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CreativeLearningsLoader:
    """Extract creative performance learnings from prior pipeline runs."""

    def load(self, previous_outputs: dict[str, Any] | None) -> dict[str, Any]:
        """Extract creative performance learnings from previous outputs.

        Looks for image style winners, hook pattern winners, copy length
        insights, and CTA performance data from prior campaign results.

        Args:
            previous_outputs: Dict of previous pipeline outputs keyed by
                node name or campaign ID.

        Returns:
            Dict with available flag and learning categories.
        """
        if not previous_outputs:
            logger.info("No previous outputs — first campaign, empty learnings")
            return self._empty_learnings()

        image_style_winners = self._extract_image_learnings(previous_outputs)
        hook_pattern_winners = self._extract_hook_learnings(previous_outputs)
        copy_length_insights = self._extract_copy_length_learnings(previous_outputs)
        cta_performance = self._extract_cta_learnings(previous_outputs)

        has_learnings = bool(
            image_style_winners
            or hook_pattern_winners
            or copy_length_insights
            or cta_performance
        )

        if has_learnings:
            logger.info(
                "Creative learnings loaded: %d image styles, "
                "%d hook patterns, %d copy insights, %d CTA insights",
                len(image_style_winners),
                len(hook_pattern_winners),
                len(copy_length_insights),
                len(cta_performance),
            )
        else:
            logger.info("No actionable creative learnings found")

        return {
            "available": has_learnings,
            "image_style_winners": image_style_winners,
            "hook_pattern_winners": hook_pattern_winners,
            "copy_length_insights": copy_length_insights,
            "cta_performance": cta_performance,
        }

    def _empty_learnings(self) -> dict[str, Any]:
        """Return empty learnings structure for first campaign."""
        return {
            "available": False,
            "image_style_winners": [],
            "hook_pattern_winners": [],
            "copy_length_insights": {},
            "cta_performance": {},
        }

    def _extract_image_learnings(self, outputs: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract winning image styles from prior creative results."""
        winners: list[dict[str, Any]] = []

        creative_results = outputs.get("creative_generation", {})
        if not creative_results:
            creative_results = outputs.get("cga", {})

        packages = creative_results.get("ad_set_packages", [])
        for pkg in packages:
            for unit in pkg.get("creative_units", []):
                ctr = unit.get("performance", {}).get("ctr", 0)
                if ctr > 0:
                    winners.append(
                        {
                            "style": unit.get("image_style", ""),
                            "funnel_stage": unit.get("funnel_stage", ""),
                            "ctr": ctr,
                            "prompt_keywords": unit.get("prompt_keywords", []),
                        }
                    )

        # Sort by CTR descending, keep top performers
        winners.sort(key=lambda w: w.get("ctr", 0), reverse=True)
        return winners[:10]

    def _extract_hook_learnings(self, outputs: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract winning hook patterns from prior results."""
        winners: list[dict[str, Any]] = []

        creative_results = outputs.get("creative_generation", {})
        if not creative_results:
            creative_results = outputs.get("cga", {})

        packages = creative_results.get("ad_set_packages", [])
        for pkg in packages:
            for unit in pkg.get("creative_units", []):
                hook = unit.get("hook", "")
                scroll_stop = unit.get("performance", {}).get("scroll_stop_rate", 0)
                if hook and scroll_stop > 0:
                    winners.append(
                        {
                            "hook_pattern": hook[:50],
                            "funnel_stage": unit.get("funnel_stage", ""),
                            "scroll_stop_rate": scroll_stop,
                        }
                    )

        winners.sort(key=lambda w: w.get("scroll_stop_rate", 0), reverse=True)
        return winners[:10]

    def _extract_copy_length_learnings(self, outputs: dict[str, Any]) -> dict[str, Any]:
        """Extract copy length performance insights."""
        insights: dict[str, Any] = {}

        creative_results = outputs.get("creative_generation", {})
        if not creative_results:
            creative_results = outputs.get("cga", {})

        packages = creative_results.get("ad_set_packages", [])
        for pkg in packages:
            funnel = pkg.get("funnel_stage", "unknown")
            for unit in pkg.get("creative_units", []):
                length_label = unit.get("copy_length", "")
                engagement = unit.get("performance", {}).get("engagement_rate", 0)
                if length_label and engagement > 0:
                    if funnel not in insights:
                        insights[funnel] = {}
                    current = insights[funnel].get(length_label, 0)
                    insights[funnel][length_label] = max(current, engagement)

        return insights

    def _extract_cta_learnings(self, outputs: dict[str, Any]) -> dict[str, Any]:
        """Extract CTA button performance data."""
        performance: dict[str, Any] = {}

        creative_results = outputs.get("creative_generation", {})
        if not creative_results:
            creative_results = outputs.get("cga", {})

        packages = creative_results.get("ad_set_packages", [])
        for pkg in packages:
            for unit in pkg.get("creative_units", []):
                cta = unit.get("cta_button", "")
                conv_rate = unit.get("performance", {}).get("conversion_rate", 0)
                if cta and conv_rate > 0:
                    current = performance.get(cta, {}).get("avg_conversion_rate", 0)
                    performance[cta] = {
                        "avg_conversion_rate": max(current, conv_rate),
                        "funnel_stage": unit.get("funnel_stage", ""),
                    }

        return performance
