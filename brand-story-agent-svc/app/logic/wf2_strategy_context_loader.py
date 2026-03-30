"""SKL-BSA-01: Load full WF2 strategy context (all prior agents) + Company seeds."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WF2StrategyContextLoader:
    """Consolidates all WF2 agent outputs into a unified strategy context."""

    async def load(self, context: dict[str, Any]) -> dict[str, Any]:
        """Build WF2 strategy context from merged context."""
        strategy = {
            "positioning": self._extract_positioning(context.get("bpa", {})),
            "architecture": self._extract_architecture(context.get("baa", {})),
            "personality": self._extract_personality(context.get("bpv", {})),
            "naming": self._extract_naming(context.get("nta", {})),
            "company_seeds": self._extract_company(context.get("company", {})),
            "audience_insights": self._extract_audience(context.get("apa", {})),
            "competitive_landscape": self._extract_competitive(context.get("cia", {})),
            "market_context": self._extract_market(context.get("mra", {})),
        }
        logger.info(
            "WF2 strategy context loaded: %d sections populated",
            sum(1 for v in strategy.values() if v),
        )
        return strategy

    def _extract_positioning(self, bpa: dict) -> dict[str, Any]:
        """Extract positioning essence from BPA output."""
        if not bpa:
            return {}
        return {
            "positioning_statement": bpa.get("positioning_statement", ""),
            "value_proposition": bpa.get("value_proposition", ""),
            "differentiators": bpa.get("differentiators", []),
            "target_market": bpa.get("target_market", ""),
            "competitive_frame": bpa.get("competitive_frame", ""),
        }

    def _extract_architecture(self, baa: dict) -> dict[str, Any]:
        """Extract architecture hierarchy from BAA output."""
        if not baa:
            return {}
        return {
            "architecture_type": baa.get("architecture_type", ""),
            "hierarchy": baa.get("hierarchy", {}),
            "sub_brands": baa.get("sub_brands", []),
            "brand_relationships": baa.get("brand_relationships", []),
        }

    def _extract_personality(self, bpv: dict) -> dict[str, Any]:
        """Extract personality dimensions from BPV output."""
        if not bpv:
            return {}
        return {
            "archetype": bpv.get("archetype", ""),
            "aaker_dimensions": bpv.get("aaker_dimensions", {}),
            "brand_values": bpv.get("brand_values", []),
            "voice_matrix": bpv.get("voice_matrix", {}),
            "tone_spectrum": bpv.get("tone_spectrum", {}),
        }

    def _extract_naming(self, nta: dict) -> dict[str, Any]:
        """Extract naming decisions from NTA output."""
        if not nta:
            return {}
        return {
            "recommended_name": nta.get("naming_brief", {}).get(
                "recommended_name", ""
            ),
            "recommended_tagline": nta.get("naming_brief", {}).get(
                "recommended_tagline", ""
            ),
            "shortlisted_names": nta.get("shortlisted_names", []),
            "taglines": nta.get("taglines", []),
        }

    def _extract_company(self, company: dict) -> dict[str, Any]:
        """Extract Company model seeds."""
        if not company:
            return {}
        return {
            "name": company.get("name", ""),
            "industry": company.get("industry", ""),
            "description": company.get("description", ""),
            "mission": company.get("mission", ""),
            "vision": company.get("vision", ""),
            "founding_story": company.get("founding_story", ""),
            "values": company.get("values", []),
            "products": company.get("products", []),
        }

    def _extract_audience(self, apa: dict) -> dict[str, Any]:
        """Extract audience insights for emotional arc."""
        if not apa:
            return {}
        return {
            "primary_persona": apa.get("primary_persona", {}),
            "emotional_drivers": apa.get("emotional_drivers", []),
            "pain_points": apa.get("pain_points", []),
            "aspirations": apa.get("aspirations", []),
        }

    def _extract_competitive(self, cia: dict) -> dict[str, Any]:
        """Extract competitive narrative landscape."""
        if not cia:
            return {}
        return {
            "competitors": cia.get("competitors", []),
            "narrative_patterns": cia.get("narrative_patterns", []),
            "differentiation_gaps": cia.get("differentiation_gaps", []),
        }

    def _extract_market(self, mra: dict) -> dict[str, Any]:
        """Extract market context for narrative grounding."""
        if not mra:
            return {}
        return {
            "market_size": mra.get("market_size", ""),
            "growth_trends": mra.get("growth_trends", []),
            "industry_context": mra.get("industry_context", ""),
        }
