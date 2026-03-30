"""SKL-NTA-11: Build Claude prompt for tagline generation."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TaglineSynthesizer:
    """Build prompts for Claude-powered tagline synthesis."""

    def build_system_prompt(self) -> str:
        """Build system prompt for tagline synthesis."""
        return (
            "You are a Brand Tagline & Slogan specialist. You create memorable, "
            "emotionally resonant taglines that amplify brand names and reinforce "
            "brand positioning.\n\n"
            "## Tagline Principles\n"
            "- 3-7 words ideal length\n"
            "- Must be memorable and easy to recall\n"
            "- Should evoke emotion and reinforce positioning\n"
            "- Must work across channels (print, digital, audio)\n"
            "- Should complement the brand name, not repeat it\n\n"
            "## Required Output (JSON)\n"
            "Return a JSON object with these keys:\n"
            "- taglines: [{tagline, name, emotional_appeal, "
            "memorability_score (0-100), positioning_alignment}]\n"
            "  Generate 2-3 taglines per shortlisted name.\n"
            "- naming_brief: {recommended_name, recommended_tagline, "
            "rationale, positioning_alignment, personality_alignment, "
            "architecture_fit, next_steps: []}\n"
            "- confidence_score: 0.0-1.0\n"
            "- findings: []\n"
            "- recommendations: []\n"
            "- sources: []\n"
        )

    def build_user_prompt(
        self,
        prompt: str,
        shortlisted: list[dict[str, Any]],
        context: dict[str, Any],
        identity_seed: dict[str, Any],
    ) -> str:
        """Build user prompt with shortlisted names and context."""
        parts = [f"Tagline generation request: {prompt}\n"]

        # Shortlisted names
        parts.append("## Shortlisted Brand Names\n")
        for i, candidate in enumerate(shortlisted, 1):
            name = candidate.get("name", "")
            rationale = candidate.get("rationale", "")
            scores = candidate.get("scores", {})
            parts.append(
                f"{i}. **{name}** — {rationale}\n"
                f"   Scores: linguistic={scores.get('linguistic', 0)}, "
                f"memorability={scores.get('memorability', 0)}, "
                f"strategy={scores.get('strategy_alignment', 0)}, "
                f"availability={scores.get('availability', 0)}\n"
            )

        if identity_seed:
            parts.append(f"\n## Brand Identity\n{_fmt(identity_seed)}\n")
        if context.get("bpa"):
            parts.append(
                f"\n## Brand Positioning\n{_fmt(context['bpa'])}\n"
            )
        if context.get("bpv"):
            parts.append(
                f"\n## Brand Personality\n{_fmt(context['bpv'])}\n"
            )
        if context.get("company"):
            parts.append(f"\n## Company\n{_fmt(context['company'])}\n")

        parts.append(
            "\n## Instructions\n"
            "1. Generate 2-3 taglines per shortlisted name above\n"
            "2. Select the best name+tagline combination as the recommendation\n"
            "3. Explain why in the naming brief\n"
            "4. Include concrete next steps for brand implementation\n"
        )

        return "\n".join(parts)


def _fmt(data: Any) -> str:
    """Format data as compact string for prompt injection."""
    return json.dumps(data, indent=None, default=str)[:3000]
