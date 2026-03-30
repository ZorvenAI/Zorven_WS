"""SKL-CAA-01: Strategy Context Loader.

Consolidates WF1 + WF2 + Company into a unified CampaignStrategyContext
dict consumed by downstream skills and LLM prompt builders.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class StrategyContextLoader:
    """Consolidate all upstream context into campaign strategy context."""

    def build_context(
        self,
        wf1_context: dict[str, Any] | None,
        bpa_context: dict[str, Any] | None,
        wf2_chain_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
        baa_context: dict[str, Any] | None = None,
        odoo_context: dict[str, Any] | None = None,
        rag_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build unified CampaignStrategyContext from all sources."""
        ctx: dict[str, Any] = {}

        # Company basics
        if company_context:
            ctx["company_name"] = company_context.get("name", "")
            ctx["industry"] = company_context.get("industry", "")
            ctx["description"] = company_context.get("description", "")
            ctx["products"] = company_context.get("products", [])
            ctx["target_markets"] = company_context.get("target_markets", [])
            ctx["website"] = company_context.get("website", "")

        # WF1 Brand Discovery insights
        if wf1_context:
            ctx["market_research"] = wf1_context.get("market_research", {})
            ctx["competitor_intelligence"] = wf1_context.get(
                "competitor_intelligence", {}
            )
            ctx["audience_personas"] = wf1_context.get("audience_persona", {})
            ctx["trend_insights"] = wf1_context.get("trend_cultural", {})
            ctx["voc_insights"] = wf1_context.get("voice_of_customer", {})

        # BPA Brand Positioning
        if bpa_context:
            ctx["positioning"] = {
                "statement": bpa_context.get("positioning_statement", ""),
                "differentiators": bpa_context.get("differentiators", []),
                "value_proposition": bpa_context.get("value_proposition", ""),
                "perceptual_map": bpa_context.get("perceptual_map", {}),
                "competitive_advantage": bpa_context.get("competitive_advantage", ""),
            }

        # WF2 chain (BPV + NTA + BSA)
        if wf2_chain_context:
            ctx["brand_personality"] = wf2_chain_context.get("brand_personality", {})
            ctx["brand_naming"] = wf2_chain_context.get("brand_naming", {})
            ctx["brand_story"] = wf2_chain_context.get("brand_story", {})

        # BAA Brand Architecture (optional)
        if baa_context:
            ctx["brand_architecture"] = {
                "hierarchy": baa_context.get("hierarchy_tree", {}),
                "sub_brands": baa_context.get("sub_brands", []),
                "portfolio_strategy": baa_context.get("portfolio_strategy", ""),
            }

        # Odoo CRM data (optional)
        if odoo_context:
            ctx["customer_data"] = {
                "total_customers": odoo_context.get("total_customers", 0),
                "segments": odoo_context.get("segments", []),
                "high_value_customers": odoo_context.get("high_value_customers", []),
            }

        # RAG prior campaign learnings (optional)
        if rag_context:
            ctx["prior_learnings"] = rag_context.get("learnings", [])

        # Brand maturity assessment
        ctx["brand_maturity"] = self._assess_maturity(ctx)

        return ctx

    def _assess_maturity(self, ctx: dict[str, Any]) -> str:
        """Assess brand maturity level for funnel strategy."""
        has_positioning = bool(ctx.get("positioning", {}).get("statement"))
        has_personality = bool(ctx.get("brand_personality"))
        has_story = bool(ctx.get("brand_story"))
        has_customers = bool(ctx.get("customer_data", {}).get("total_customers", 0) > 0)

        score = sum([has_positioning, has_personality, has_story, has_customers])
        if score >= 3:
            return "established"
        elif score >= 1:
            return "emerging"
        return "new"
