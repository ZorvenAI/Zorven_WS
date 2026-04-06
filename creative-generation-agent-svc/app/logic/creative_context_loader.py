"""SKL-CGA-01: Creative Context Loader.

Consolidates all upstream contexts (CAA blueprint, WF1, WF2, Company)
into a unified CampaignCreativeContext dict consumed by downstream
skills and LLM prompt builders.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CreativeContextLoader:
    """Consolidate all upstream context into a campaign creative context."""

    def build_context(
        self,
        caa_context: dict[str, Any] | None,
        wf1_context: dict[str, Any] | None,
        bpa_context: dict[str, Any] | None,
        bpv_context: dict[str, Any] | None,
        nta_context: dict[str, Any] | None,
        bsa_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build unified CampaignCreativeContext from all sources.

        Args:
            caa_context: Campaign Architecture blueprint (ad sets, funnel map).
            wf1_context: WF1 Brand Discovery (APA personas, etc.).
            bpa_context: Brand Positioning (UVP, differentiators).
            bpv_context: Brand Personality (archetype, voice matrix).
            nta_context: Brand Naming (recommended name + tagline).
            bsa_context: Brand Story (story arcs, narratives).
            company_context: Company model (colors, logo, industry).

        Returns:
            Unified creative context dict.
        """
        ctx: dict[str, Any] = {
            "creative_briefs": self._extract_creative_briefs(caa_context),
            "brand_visual": self._extract_brand_visual(bpv_context, company_context),
            "brand_voice": self._extract_brand_voice(bpv_context),
            "positioning": self._extract_positioning(bpa_context),
            "name_tagline": self._extract_name_tagline(nta_context),
            "story_arcs": self._extract_story_arcs(bsa_context),
            "audience_personas": self._extract_audience_personas(wf1_context),
            "company": self._extract_company(company_context),
        }

        logger.info(
            "Creative context loaded: %d sections populated, %d creative briefs",
            sum(1 for v in ctx.values() if v),
            len(ctx.get("creative_briefs", [])),
        )
        return ctx

    def _extract_creative_briefs(
        self, caa_context: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Extract creative briefs from CAA blueprint ad sets.

        Each brief represents an audience x funnel combination requiring
        creative assets.
        """
        if not caa_context:
            return []

        briefs: list[dict[str, Any]] = []

        # Prefer explicit creative_briefs, else unwrap blueprint.ad_sets,
        # else fall back to top-level ad_sets.
        ad_sets = caa_context.get("creative_briefs", [])
        if not ad_sets:
            blueprint = caa_context.get("blueprint", {})
            if isinstance(blueprint, dict):
                ad_sets = blueprint.get("ad_sets", [])
        if not ad_sets:
            ad_sets = caa_context.get("ad_sets", [])

        # Defensive: upstream CAA may return a malformed blueprint where
        # ad_sets is an int, dict, or other non-iterable. Coerce to list.
        if not isinstance(ad_sets, list):
            ad_sets = []

        for ad_set in ad_sets:
            if not isinstance(ad_set, dict):
                continue
            brief: dict[str, Any] = {
                # Prefer CAA-style keys, fall back to blueprint-style keys
                "ad_set_name": ad_set.get("ad_set_name") or ad_set.get("name", ""),
                "persona": ad_set.get("persona")
                or ad_set.get("persona_name")
                or ad_set.get("targeting", {}).get("persona")
                or ad_set.get("targeting", {}).get("persona_name", ""),
                "funnel_stage": ad_set.get("funnel_stage")
                or ad_set.get("stage")
                or ad_set.get("funnel_stage_name", ""),
                "messaging_theme": ad_set.get("messaging_theme", ""),
                "variant_count": ad_set.get("variant_count", 3),
                "placements": ad_set.get("placements", []),
                "objective": ad_set.get("objective", ""),
            }
            briefs.append(brief)

        return briefs

    def _extract_brand_visual(
        self,
        bpv_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Extract brand visual identity from BPV + Company.

        Combines archetype mood from BPV with Company visual assets.
        """
        visual: dict[str, Any] = {}

        if bpv_context:
            archetype_raw = bpv_context.get("archetype", "")
            # Normalize archetype to a string for prompt embedding
            if isinstance(archetype_raw, dict):
                archetype_raw = archetype_raw.get("primary", archetype_raw)
                if isinstance(archetype_raw, dict):
                    archetype_raw = archetype_raw.get("name", "")
            visual["archetype"] = archetype_raw
            visual["mood"] = bpv_context.get("tone_spectrum", {}).get(
                "primary_mood", str(archetype_raw)
            )
            visual["aaker_dimensions"] = bpv_context.get("aaker_dimensions", {})

        if company_context:
            visual["color_palette_desc"] = company_context.get("color_palette_desc", "")
            visual["logo_url"] = company_context.get("logo_url", "")
            visual["industry"] = company_context.get("industry", "")

        return visual

    def _extract_brand_voice(
        self, bpv_context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Extract brand voice matrix from BPV personality output."""
        if not bpv_context:
            return {}
        return {
            "voice_matrix": bpv_context.get("voice_matrix", {}),
            "tone_spectrum": bpv_context.get("tone_spectrum", {}),
            "brand_values": bpv_context.get("brand_values", []),
        }

    def _extract_positioning(
        self, bpa_context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Extract positioning essence from BPA output."""
        if not bpa_context:
            return {}
        return {
            "uvp": bpa_context.get(
                "value_proposition",
                bpa_context.get("unique_value_proposition", ""),
            ),
            "key_benefit": bpa_context.get("key_benefit", ""),
            "positioning_statement": bpa_context.get("positioning_statement", ""),
            "differentiators": bpa_context.get("differentiators", []),
            "competitive_advantage": bpa_context.get("competitive_advantage", ""),
        }

    def _extract_name_tagline(
        self, nta_context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Extract brand name and tagline from NTA output."""
        if not nta_context:
            return {}

        naming_brief = nta_context.get("naming_brief", {})
        return {
            "brand_name": naming_brief.get(
                "recommended_name",
                nta_context.get("recommended_name", ""),
            ),
            "tagline": naming_brief.get(
                "recommended_tagline",
                nta_context.get("recommended_tagline", ""),
            ),
            "tagline_variants": nta_context.get("taglines", []),
        }

    def _extract_story_arcs(self, bsa_context: dict[str, Any] | None) -> dict[str, Any]:
        """Extract brand story arcs from BSA output."""
        if not bsa_context:
            return {}
        return {
            "origin_story": bsa_context.get("origin_story", {}),
            "mission": bsa_context.get("mission_vision", {}).get("mission", {}),
            "vision": bsa_context.get("mission_vision", {}).get("vision", {}),
            "pitches": bsa_context.get("pitches", {}),
            "channel_narratives": bsa_context.get("channel_narratives", {}),
        }

    def _extract_audience_personas(
        self, wf1_context: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        """Extract audience personas from WF1 APA output."""
        if not wf1_context:
            return []

        apa = wf1_context.get("audience_persona", {})
        return apa.get("personas", [])

    def _extract_company(
        self, company_context: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Extract Company model fields."""
        if not company_context:
            return {}
        return {
            "name": company_context.get("name", ""),
            "industry": company_context.get("industry", ""),
            "description": company_context.get("description", ""),
            "products": company_context.get("products", []),
            "website": company_context.get("website", ""),
        }
