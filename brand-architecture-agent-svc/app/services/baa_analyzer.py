"""BAA Analyzer — PAOR engine for brand architecture analysis.

Three-phase execution:
  Phase 1 — Research (parallel): SKL-BAA-01..05
  Phase 2 — Architecture Design (sequential): SKL-BAA-06..10
  Phase 3 — Persist + Escalation: SKL-BAA-11..12
"""

import logging
import time
from typing import Any

from app.messaging.event_emitter import EventEmitter, EventType
from app.services.anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)


class BAAAnalyzer:
    """PAOR engine for brand architecture analysis."""

    def __init__(
        self,
        anthropic_client: AnthropicClient | None,
        event_emitter: EventEmitter,
        prompt_loader: Any = None,
    ) -> None:
        self._llm = anthropic_client
        self._events = event_emitter
        self._prompt_loader = prompt_loader

    async def analyze(
        self,
        prompt: str,
        tenant_id: str,
        user_role: str,
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        wf1_context: dict[str, Any],
        bpa_context: dict[str, Any],
        company_context: dict[str, Any],
        skill_context: str = "",
    ) -> dict[str, Any]:
        """Execute the full BAA analysis pipeline.

        Args:
            prompt: User's architecture request
            tenant_id: Tenant identifier
            user_role: User's RBAC role
            config: Execution config
            previous_outputs: Upstream node outputs from orchestrator
            wf1_context: WF1 Brand Discovery data from Django
            bpa_context: BPA Brand Positioning data from Django
            company_context: Company model + product portfolio
            skill_context: Optional skill injection from orchestrator

        Returns:
            Complete architecture strategy result dict.
        """
        start_ms = time.time()

        # Merge all contexts
        context = self._merge_context(
            wf1_context, bpa_context, company_context, previous_outputs
        )

        # Phase 1: Research (gather intelligence)
        research = await self._phase_research(prompt, tenant_id, context, skill_context)

        # Phase 2: Architecture Design (generate via Claude)
        if not self._llm:
            return self._stub_result(prompt, start_ms)

        synthesis = await self._phase_design(
            prompt, tenant_id, context, research, skill_context
        )

        # Phase 3: Persist + Escalation check
        await self._phase_persist(tenant_id, synthesis)

        elapsed_ms = int((time.time() - start_ms) * 1000)

        return {
            "query": prompt,
            "recommendation": synthesis.get("recommendation", {}),
            "hierarchy": synthesis.get("hierarchy", {}),
            "naming_hierarchy": synthesis.get("naming_hierarchy", {}),
            "growth_path": synthesis.get("growth_path", {}),
            "strategy": synthesis.get("strategy", {}),
            "confidence_score": synthesis.get("confidence_score", 0.0),
            "wf1_context_used": bool(wf1_context),
            "bpa_context_used": bool(bpa_context),
            "execution_time_ms": elapsed_ms,
            "findings": synthesis.get("findings", []),
            "recommendations": synthesis.get("recommendations", []),
            "sources": synthesis.get("sources", []),
        }

    def _merge_context(
        self,
        wf1_context: dict[str, Any],
        bpa_context: dict[str, Any],
        company_context: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge WF1 + BPA + Company + previous_outputs into unified context."""
        merged: dict[str, Any] = {}

        # WF1 context (from Django endpoint)
        if wf1_context:
            merged["mra"] = wf1_context.get("mra", {})
            merged["cia"] = wf1_context.get("cia", {})
            merged["apa"] = wf1_context.get("apa", {})
            merged["tcia"] = wf1_context.get("tcia", {})
            merged["voca"] = wf1_context.get("voca", {})

        # BPA context (from Django endpoint)
        if bpa_context:
            merged["bpa"] = bpa_context

        # Company context (from Django endpoint)
        if company_context:
            merged["company"] = company_context

        # Previous outputs (from orchestrator pipeline)
        if previous_outputs:
            if "market_research" in previous_outputs:
                merged["mra"] = previous_outputs["market_research"]
            if "competitor_intelligence" in previous_outputs:
                merged["cia"] = previous_outputs["competitor_intelligence"]
            if "audience_persona" in previous_outputs:
                merged["apa"] = previous_outputs["audience_persona"]
            if "trend_cultural" in previous_outputs:
                merged["tcia"] = previous_outputs["trend_cultural"]
            if "voice_of_customer" in previous_outputs:
                merged["voca"] = previous_outputs["voice_of_customer"]
            if "brand_positioning" in previous_outputs:
                merged["bpa"] = previous_outputs["brand_positioning"]

        return merged

    async def _phase_research(
        self,
        prompt: str,
        tenant_id: str,
        context: dict[str, Any],
        skill_context: str,
    ) -> dict[str, Any]:
        """Phase 1: Research — gather competitive, audience, portfolio data."""
        research = {
            "competitive_architectures": self._extract_competitive_arch(context),
            "audience_alignment": self._extract_audience_alignment(context),
            "portfolio_data": self._extract_portfolio(context),
            "positioning_strategy": self._extract_positioning(context),
            "prior_architecture": {},
        }
        return research

    def _extract_competitive_arch(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract competitor architecture patterns from CIA data."""
        cia = context.get("cia", {})
        return {
            "competitors": (
                cia.get("competitors_analyzed", []) or cia.get("competitors", [])
            ),
            "market_positions": cia.get("market_positions", []),
            "swot": cia.get("swot_analysis", {}),
        }

    def _extract_audience_alignment(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract audience data from APA + VoCA + BPA needs hierarchy."""
        apa = context.get("apa", {})
        voca = context.get("voca", {})
        bpa = context.get("bpa", {})
        return {
            "personas": apa.get("personas", []),
            "pain_points": (
                voca.get("pain_point_priority_matrix", {}).get("pain_points", [])
            ),
            "sentiment": voca.get("sentiment", {}),
            "needs_hierarchy": bpa.get("differentiation", {}).get("pods", []),
        }

    def _extract_portfolio(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract portfolio from Company context."""
        company = context.get("company", {})
        return {
            "company_name": company.get("name", ""),
            "industry": company.get("industry", ""),
            "description": company.get("description", ""),
            "brand_voice": company.get("brand_voice", ""),
            "values": company.get("values", ""),
            "target_audience": company.get("target_audience", ""),
            "products": company.get("products", []),
        }

    def _extract_positioning(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract BPA positioning strategy."""
        bpa = context.get("bpa", {})
        return {
            "recommended_positioning": bpa.get("recommended_positioning", {}),
            "positioning_candidates": bpa.get("positioning_candidates", []),
            "canvas": bpa.get("canvas", {}),
            "perceptual_maps": bpa.get("perceptual_maps", []),
            "differentiation": bpa.get("differentiation", {}),
            "confidence_score": bpa.get("confidence_score", 0.0),
        }

    async def _phase_design(
        self,
        prompt: str,
        tenant_id: str,
        context: dict[str, Any],
        research: dict[str, Any],
        skill_context: str,
    ) -> dict[str, Any]:
        """Phase 2: Architecture Design — generate via Claude."""
        if self._prompt_loader:
            from app.prompts.fallbacks import FALLBACK_HIERARCHY

            system_prompt = await self._prompt_loader.load(
                "zorven-wf2-baa-hierarchy",
                tenant_id=tenant_id or None,
                fallback=FALLBACK_HIERARCHY,
            )
            if skill_context:
                system_prompt += f"\n\nAdditional context:\n{skill_context}"
        else:
            system_prompt = self._build_system_prompt(skill_context)
        user_prompt = self._build_user_prompt(prompt, context, research)

        result = await self._llm.generate_json(system_prompt, user_prompt)

        # Detect parse failure (raw_text key present means JSON parsing failed)
        if "raw_text" in result and "recommendation" not in result:
            logger.error(
                "Claude returned unparseable response for tenant %s "
                "(raw_text length=%d)",
                tenant_id,
                len(result.get("raw_text", "")),
            )
            return {
                "recommendation": {},
                "hierarchy": {},
                "naming_hierarchy": {},
                "growth_path": {},
                "strategy": {},
                "confidence_score": 0.0,
                "findings": result.get(
                    "findings",
                    [
                        "Architecture analysis completed but the response "
                        "could not be parsed. Please retry the analysis."
                    ],
                ),
                "recommendations": [],
                "sources": [],
            }

        # Extract and structure the response
        recommendation = result.get("recommendation", {})
        hierarchy = result.get("hierarchy", {})
        naming = result.get("naming_hierarchy", {})
        growth = result.get("growth_path", {})

        return {
            "recommendation": recommendation,
            "hierarchy": hierarchy,
            "naming_hierarchy": naming,
            "growth_path": growth,
            "strategy": result.get("strategy", {}),
            "confidence_score": result.get("confidence_score", 0.0),
            "findings": result.get("findings", []),
            "recommendations": result.get("recommendations", []),
            "sources": result.get("sources", []),
        }

    async def _phase_persist(self, tenant_id: str, synthesis: dict[str, Any]) -> None:
        """Phase 3: Persist strategy + escalation check."""
        confidence = synthesis.get("confidence_score", 0.0)

        # Emit persistence event
        await self._events.emit(
            EventType.STRATEGY_PERSISTED,
            tenant_id=tenant_id,
            data={"confidence_score": confidence},
        )

        # Check for escalation triggers
        if confidence < 0.5:
            await self._events.emit(
                EventType.HUMAN_ESCALATION,
                tenant_id=tenant_id,
                data={
                    "reason": "low_confidence",
                    "confidence_score": confidence,
                },
            )

    def _build_system_prompt(self, skill_context: str = "") -> str:
        """Build the system prompt for Claude architecture analysis."""
        base = (
            "You are a brand architecture strategist AI. Design optimal "
            "brand structures and hierarchies using established frameworks.\n\n"
            "Respond with valid JSON containing these top-level keys:\n"
            "- recommendation: architecture model recommendation object\n"
            "- hierarchy: brand hierarchy tree object\n"
            "- naming_hierarchy: naming conventions object\n"
            "- growth_path: portfolio growth roadmap object\n"
            "- strategy: full architecture strategy document object\n"
            "- confidence_score: float 0-1\n"
            "- findings: array of key findings strings\n"
            "- recommendations: array of strategic recommendation strings\n"
            "- sources: array of data source reference objects\n\n"
            "recommendation must include:\n"
            "- recommended_model: one of branded_house, house_of_brands, "
            "endorsed, hybrid, sub_brand\n"
            "- model_scores: array of 5 model evaluations, each with:\n"
            "  - model, positioning_alignment (0-25), audience_fit (0-25), "
            "competitive_diff (0-25), operational_efficiency (0-25), "
            "total (0-100), rationale\n"
            "- why_not_others: array of rejection rationales for non-selected\n"
            "- confidence_score: 0-1\n"
            "- citations: evidence references\n\n"
            "hierarchy must include:\n"
            "- root: recursive node with name, type (master|sub_brand|"
            "product_line|endorsed|independent), relationship_to_parent, "
            "target_persona, positioning_score (0-100), "
            "visual_identity_guideline, children (recursive)\n"
            "- total_depth: integer\n"
            "- total_nodes: integer\n\n"
            "naming_hierarchy must include:\n"
            "- naming_pattern: descriptive pattern name\n"
            "- naming_rules: array of rule objects\n"
            "- consistency_score: 0-100\n\n"
            "growth_path must include:\n"
            "- phases: array of phase objects with timeline, actions, metrics\n"
            "- portfolio_risk_assessment: array of risk objects\n"
        )
        if skill_context:
            base += f"\n\nAdditional context:\n{skill_context}"
        return base

    def _build_user_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
        research: dict[str, Any],
    ) -> str:
        """Build the user prompt with all research context."""
        import json

        sections = [f"Brand Architecture Request: {prompt}\n"]

        # Portfolio data
        portfolio = research.get("portfolio_data", {})
        if portfolio.get("company_name"):
            sections.append(
                "## Company & Portfolio\n"
                + json.dumps(portfolio, indent=2, default=str)[:3000]
            )

        # Positioning strategy (from BPA)
        positioning = research.get("positioning_strategy", {})
        if positioning.get("recommended_positioning"):
            sections.append(
                "## Brand Positioning Strategy (from BPA)\n"
                + json.dumps(positioning, indent=2, default=str)[:3000]
            )

        # Competitive architectures
        comp_arch = research.get("competitive_architectures", {})
        if comp_arch.get("competitors"):
            sections.append(
                "## Competitive Landscape\n"
                + json.dumps(comp_arch, indent=2, default=str)[:3000]
            )

        # Audience alignment
        audience = research.get("audience_alignment", {})
        if audience.get("personas"):
            sections.append(
                "## Audience Alignment\n"
                + json.dumps(audience, indent=2, default=str)[:3000]
            )

        # Market research
        mra = context.get("mra", {})
        if mra:
            sections.append(
                "## Market Research\n" + json.dumps(mra, indent=2, default=str)[:2000]
            )

        return "\n\n".join(sections)

    def _stub_result(self, prompt: str, start_time: float) -> dict[str, Any]:
        """Return stub result when LLM is unavailable."""
        elapsed_ms = int((time.time() - start_time) * 1000)
        return {
            "query": prompt,
            "recommendation": {
                "recommended_model": "hybrid",
                "model_scores": [],
                "why_not_others": [],
                "confidence_score": 0.0,
                "citations": [],
            },
            "hierarchy": {
                "root": {
                    "name": "Stub Brand",
                    "type": "master",
                    "relationship_to_parent": "root",
                    "children": [],
                },
                "total_depth": 1,
                "total_nodes": 1,
            },
            "naming_hierarchy": {
                "naming_pattern": "Stub — LLM unavailable",
                "naming_rules": [],
                "consistency_score": 0.0,
            },
            "growth_path": {
                "phases": [],
                "portfolio_risk_assessment": [],
            },
            "strategy": {},
            "confidence_score": 0.0,
            "wf1_context_used": False,
            "bpa_context_used": False,
            "execution_time_ms": elapsed_ms,
            "findings": ["LLM unavailable — stub response returned"],
            "recommendations": [],
            "sources": [],
        }
