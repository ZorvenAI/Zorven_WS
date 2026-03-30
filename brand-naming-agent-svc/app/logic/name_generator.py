"""SKL-NTA-09: Build Claude system/user prompt for name generation."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

NAMING_TYPES = [
    "Descriptive — directly describes what the brand does",
    "Coined/Invented — new word with no prior meaning (e.g., Kodak, Xerox)",
    "Metaphorical — evokes imagery or associations (e.g., Amazon, Nike)",
    "Acronym/Initialism — abbreviation of longer name (e.g., IBM, BMW)",
    "Compound — combines two words (e.g., Facebook, YouTube)",
    "Abstract — suggestive but not literal (e.g., Apple, Oracle)",
    "Founder-based — derived from person's name (e.g., Ford, Disney)",
]


class NameGenerator:
    """Build prompts for Claude-powered brand name generation."""

    def build_system_prompt(self) -> str:
        """Build system prompt for name generation."""
        return (
            "You are a Brand Naming strategist with expertise in linguistics, "
            "semiotics, and brand architecture. You create memorable, distinctive "
            "brand names that align with brand positioning and personality.\n\n"
            "## Naming Types\n"
            + "\n".join(f"- {t}" for t in NAMING_TYPES)
            + "\n\n"
            "## Scoring Dimensions (each 0-100)\n"
            "1. Linguistic — pronunciation ease, phonetic appeal, cross-language safety\n"
            "2. Memorability — distinctiveness, recall potential, simplicity\n"
            "3. Strategy Alignment — fit with positioning, personality, values\n"
            "\n"
            "## Required Output (JSON)\n"
            "Return a JSON object with these keys:\n"
            "- name_candidates: [{name, rationale, naming_type, "
            "scores: {linguistic, memorability, strategy_alignment}}]\n"
            "  Generate 7-15 candidates across multiple naming types.\n"
            "- confidence_score: 0.0-1.0\n"
            "- findings: []\n"
            "- recommendations: []\n"
            "- sources: []\n\n"
            "Each name MUST:\n"
            "- Be 1-3 words maximum\n"
            "- Be easy to pronounce in English\n"
            "- Not be an existing well-known brand\n"
            "- Include a rationale explaining the name's meaning and appeal\n"
            "- Use a variety of naming types\n"
        )

    def build_user_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
        audience_psych: dict[str, Any],
        competitive: dict[str, Any],
        identity_seed: dict[str, Any],
        brand_ctx: dict[str, Any],
        rag_docs: dict[str, Any],
    ) -> str:
        """Build user prompt with all research context."""
        parts = [f"Brand naming request: {prompt}\n"]

        if identity_seed:
            parts.append(f"## Brand Identity Seed\n{_fmt(identity_seed)}\n")
        if audience_psych:
            parts.append(f"## Audience Psychology\n{_fmt(audience_psych)}\n")
        if competitive:
            parts.append(
                f"## Competitive Naming Landscape\n{_fmt(competitive)}\n"
            )
        if brand_ctx and brand_ctx.get("has_architecture"):
            parts.append(
                f"## Brand Architecture Context\n{_fmt(brand_ctx)}\n"
            )
        if context.get("bpa"):
            parts.append(
                f"## Brand Positioning\n{_fmt(context['bpa'])}\n"
            )
        if context.get("company"):
            parts.append(f"## Company\n{_fmt(context['company'])}\n")
        if rag_docs and rag_docs.get("documents"):
            docs_text = _fmt(rag_docs["documents"])
            parts.append(
                f"## Relevant Brand Documents (RAG)\n{docs_text}\n"
            )

        if competitive.get("white_space_types"):
            parts.append(
                "\n## White Space Opportunity\n"
                "Competitors underuse these naming types: "
                f"{', '.join(competitive['white_space_types'])}. "
                "Consider generating candidates in these categories.\n"
            )

        if brand_ctx.get("naming_constraints"):
            parts.append(
                "\n## Architecture Constraints\n"
                + "\n".join(
                    f"- {c}" for c in brand_ctx["naming_constraints"]
                )
                + "\n"
            )

        return "\n".join(parts)


def _fmt(data: Any) -> str:
    """Format data as compact string for prompt injection."""
    return json.dumps(data, indent=None, default=str)[:3000]
