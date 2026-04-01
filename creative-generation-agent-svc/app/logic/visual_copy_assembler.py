"""SKL-CGA-11: Visual Copy Assembler.

Builds a prompt section for Claude call 3 that instructs Claude to
pair approved images with copy and CTAs to produce complete ad
creative units, evaluating image-copy coherence.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Meta ad format specifications
_AD_FORMATS: dict[str, dict[str, str]] = {
    "single_image": {
        "label": "Single Image Ad",
        "specs": "1 image + headline + primary text + CTA",
        "placements": "Feed, Stories, Reels, Marketplace, Search",
    },
    "carousel": {
        "label": "Carousel Ad",
        "specs": "2-10 images, each with headline + CTA",
        "placements": "Feed, Stories, Marketplace",
    },
    "stories": {
        "label": "Stories/Reels Ad",
        "specs": "Full-screen vertical image + minimal text overlay + CTA",
        "placements": "Stories, Reels",
    },
}


class VisualCopyAssembler:
    """Builds prompt section for image-copy pairing and assembly."""

    def build_prompt_section(
        self,
        creative_context: dict[str, Any],
        generated_images: list[dict[str, Any]],
    ) -> str:
        """Build a prompt section for Claude call 3.

        Instructs Claude to pair approved images with copy and CTAs
        to produce complete ad creative units with coherence scoring.

        Args:
            creative_context: Unified CampaignCreativeContext dict.
            generated_images: List of generated image metadata dicts
                from ImageGenerator, each with ad_set_name, variant_id,
                aspect_ratio, gcs_url, prompt_used.

        Returns:
            Formatted prompt section string.
        """
        briefs = creative_context.get("creative_briefs", [])

        section = "## Visual-Copy Assembly Task\n\n"
        section += (
            "Pair the generated images with approved copy (hooks, "
            "primary text) and CTAs to produce complete ad creative "
            "units. Evaluate image-copy coherence for each pairing.\n\n"
        )

        # Available ad formats
        section += "### Available Ad Formats\n"
        for fmt_key, fmt_spec in _AD_FORMATS.items():
            section += (
                f"- **{fmt_spec['label']}** (`{fmt_key}`): "
                f"{fmt_spec['specs']}. "
                f"Placements: {fmt_spec['placements']}\n"
            )
        section += "\n"

        # Image inventory
        section += "### Generated Image Inventory\n\n"
        if not generated_images:
            section += (
                "No images were generated. Create creative units "
                "using placeholder image references.\n\n"
            )
        else:
            # Group images by ad set
            images_by_adset: dict[str, list[dict[str, Any]]] = {}
            for img in generated_images:
                ad_set = img.get("ad_set_name", "unknown")
                if ad_set not in images_by_adset:
                    images_by_adset[ad_set] = []
                images_by_adset[ad_set].append(img)

            for ad_set, images in images_by_adset.items():
                section += f"**{ad_set}**: {len(images)} images\n"
                for img in images:
                    section += (
                        f"  - `{img.get('variant_id', '')}` "
                        f"({img.get('aspect_ratio', '')}) → "
                        f"`{img.get('gcs_url', 'pending')}`\n"
                    )
            section += "\n"

        # Assembly instructions per ad set
        section += "### Assembly Instructions\n\n"
        section += (
            f"For each of the {len(briefs)} ad sets, produce "
            f"**2-4 complete creative units**. Each unit pairs:\n"
            "1. One image (by variant_id + aspect_ratio)\n"
            "2. One hook (as headline)\n"
            "3. One primary text variant (choose appropriate length "
            "for the placement)\n"
            "4. One CTA button + custom text\n"
            "5. An ad format designation\n\n"
        )

        for i, brief in enumerate(briefs, 1):
            ad_set_name = brief.get("ad_set_name", f"Ad Set {i}")
            placements = brief.get("placements", [])
            funnel = brief.get("funnel_stage", "tofu").lower()

            section += f"#### {i}. {ad_set_name}\n"
            section += f"- **Funnel**: {funnel.upper()}\n"
            if placements:
                section += (
                    f"- **Target placements**: {', '.join(placements)}\n"
                )
            section += (
                "- Match image mood with copy tone\n"
                "- Use 1:1 images for feed, 9:16 for stories/reels, "
                "16:9 for video covers\n"
                "- Ensure visual-copy narrative alignment\n\n"
            )

        # Coherence scoring
        section += "### Image-Copy Coherence Scoring\n\n"
        section += (
            "For each creative unit, evaluate and score "
            "`image_copy_coherence` from 0-100:\n"
            "- **90-100**: Image and copy tell the same story perfectly\n"
            "- **70-89**: Strong alignment with minor disconnects\n"
            "- **50-69**: Moderate alignment, some mixed signals\n"
            "- **0-49**: Poor alignment, image contradicts copy message\n\n"
            "Only include units with coherence >= 50.\n\n"
        )

        # Output format
        section += "### Creative Unit Output Format\n\n"
        section += (
            "Output a `creative_units` array. Each entry:\n"
            "```json\n"
            "{\n"
            '  "ad_set_name": "string",\n'
            '  "unit_id": "unit_01",\n'
            '  "image_variant_id": "v1",\n'
            '  "image_aspect_ratio": "1:1|9:16|16:9",\n'
            '  "image_gcs_url": "gs://...",\n'
            '  "headline": "hook text used as headline",\n'
            '  "primary_text": "primary copy variant text",\n'
            '  "copy_length": "short|medium|long",\n'
            '  "cta_button": "META_ENUM_VALUE",\n'
            '  "cta_text": "custom CTA label",\n'
            '  "ad_format": "single_image|carousel|stories",\n'
            '  "target_placement": "feed|stories|reels|marketplace",\n'
            '  "image_copy_coherence": 0-100,\n'
            '  "coherence_rationale": "why this pairing works/doesn\'t"\n'
            "}\n"
            "```\n"
        )

        return section
