"""SKL-CGA-12: Creative Package Synthesizer.

Builds the capstone prompt section for Claude call 3 that instructs
Claude to assemble the full CampaignCreativePackage JSON with all
metrics, images, copy, and quality scores.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CreativePackageSynthesizer:
    """Builds capstone prompt section for creative package assembly."""

    def build_prompt_section(self, creative_context: dict[str, Any]) -> str:
        """Build capstone prompt section for Claude call 3.

        Instructs Claude to assemble the full CampaignCreativePackage
        JSON structure with all metrics and quality scores.

        Args:
            creative_context: Unified CampaignCreativeContext dict.

        Returns:
            Formatted prompt section string.
        """
        briefs = creative_context.get("creative_briefs", [])
        name_tagline = creative_context.get("name_tagline", {})
        brand_name = name_tagline.get("brand_name", "")

        section = "## Campaign Creative Package Synthesis\n\n"
        section += (
            "Assemble the final CampaignCreativePackage JSON that "
            "consolidates all generated creative assets, compliance "
            "results, and quality metrics into a single deliverable.\n\n"
        )

        # Package requirements
        section += "### Package Requirements\n\n"
        section += f"- **Ad sets to package**: {len(briefs)}\n"
        if brand_name:
            section += f"- **Brand**: {brand_name}\n"
        section += (
            "- Each ad set package must include: images, hooks, "
            "primary copy, CTAs, creative units, compliance results\n"
            "- Calculate aggregate quality metrics across all assets\n\n"
        )

        # Quality scoring criteria
        section += "### Quality Scoring Criteria\n\n"
        section += (
            "Calculate the following aggregate scores:\n\n"
            "**creative_quality_score** (0-1):\n"
            "- Image quality and brand alignment (25%)\n"
            "- Hook scroll-stop power average (25%)\n"
            "- Copy-image coherence average (25%)\n"
            "- CTA clarity average (25%)\n\n"
            "**confidence_score** (0-1):\n"
            "- Compliance pass rate (30%)\n"
            "- Creative diversity (20%)\n"
            "- Brand voice consistency (20%)\n"
            "- Funnel coverage completeness (30%)\n\n"
        )

        # Per-ad-set package structure
        section += "### Ad Set Package Structure\n\n"
        section += (
            "Each `ad_set_packages[]` entry must contain:\n"
            "- `ad_set_name`: Name matching the blueprint\n"
            "- `persona`: Target persona\n"
            "- `funnel_stage`: TOFU/MOFU/BOFU/RETENTION\n"
            "- `images`: Array of generated image references\n"
            "- `hooks`: Array of hooks with scores\n"
            "- `primary_copy`: Array of copy variants (short/medium/long)\n"
            "- `ctas`: Array of CTA variants with scores\n"
            "- `creative_units`: Array of assembled image+copy+CTA units\n"
            "- `compliance_results`: Per-variant compliance status\n"
            "- `ad_set_quality_score`: Quality score for this ad set (0-1)\n\n"
        )

        # Output format
        section += "### CampaignCreativePackage Output Format\n\n"
        section += (
            "Output the complete package as:\n"
            "```json\n"
            "{\n"
            '  "campaign_id": "string (from blueprint)",\n'
            '  "brand_name": "string",\n'
            '  "ad_set_packages": [\n'
            "    {\n"
            '      "ad_set_name": "string",\n'
            '      "persona": "string",\n'
            '      "funnel_stage": "string",\n'
            '      "images": [{image objects}],\n'
            '      "hooks": [{hook objects with scores}],\n'
            '      "primary_copy": [{copy variant objects}],\n'
            '      "ctas": [{cta variant objects}],\n'
            '      "creative_units": [{assembled unit objects}],\n'
            '      "compliance_results": [{compliance objects}],\n'
            '      "ad_set_quality_score": 0.0-1.0\n'
            "    }\n"
            "  ],\n"
            '  "total_images_generated": int,\n'
            '  "total_images_refined": int,\n'
            '  "image_gen_cost_usd": float,\n'
            '  "compliance_pass_rate": 0.0-1.0,\n'
            '  "creative_quality_score": 0.0-1.0,\n'
            '  "confidence_score": 0.0-1.0,\n'
            '  "findings": ["insight strings"],\n'
            '  "recommendations": ["actionable recommendations"],\n'
            '  "sources": [{"label": "string", "description": "string"}]\n'
            "}\n"
            "```\n\n"
            "**Important**: Ensure all numeric scores are between 0 and 1. "
            "The `confidence_score` is the overall package confidence "
            "and will be used for human escalation decisions.\n"
        )

        return section
