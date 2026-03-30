"""SKL-NTA-12: Compile final naming brief document."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class NamingBriefBuilder:
    """Compile final naming brief from LLM output and context."""

    def build(
        self,
        llm_brief: dict[str, Any],
        shortlisted: list[dict[str, Any]],
        taglines: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build final naming brief, enriching LLM output with context."""
        brief = {
            "recommended_name": llm_brief.get("recommended_name", ""),
            "recommended_tagline": llm_brief.get("recommended_tagline", ""),
            "rationale": llm_brief.get("rationale", ""),
            "positioning_alignment": llm_brief.get(
                "positioning_alignment", ""
            ),
            "personality_alignment": llm_brief.get(
                "personality_alignment", ""
            ),
            "architecture_fit": llm_brief.get("architecture_fit", ""),
            "next_steps": llm_brief.get("next_steps", []),
        }

        # Enrich with shortlist data
        rec_name = brief["recommended_name"]
        if rec_name and shortlisted:
            for candidate in shortlisted:
                if candidate.get("name") == rec_name:
                    brief["recommended_name_scores"] = candidate.get(
                        "scores", {}
                    )
                    brief["recommended_name_availability"] = candidate.get(
                        "availability", {}
                    )
                    break

        # Count taglines for recommendation
        rec_taglines = [
            t for t in taglines
            if isinstance(t, dict) and t.get("name") == rec_name
        ]
        brief["tagline_alternatives_count"] = len(rec_taglines)

        # Add default next steps if none provided
        if not brief["next_steps"]:
            brief["next_steps"] = [
                "Conduct formal trademark search with legal counsel",
                "Register preferred domain names",
                "Secure social media handles",
                "Develop brand identity guidelines",
                "Test name with target audience focus group",
            ]

        return brief
