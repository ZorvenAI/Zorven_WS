"""BPA Analyzer — PAOR engine for brand positioning analysis.

Three-phase execution:
  Phase 1 — Research (parallel): SKL-BPA-01..05
  Phase 2 — Synthesis (sequential): SKL-BPA-06..10
  Phase 3 — Persist + Escalation: SKL-BPA-11..12
"""

import asyncio
import logging
import time
from typing import Any

from app.messaging.event_emitter import EventEmitter, EventType
from app.services.anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)


class BPAAnalyzer:
    """PAOR engine for brand positioning analysis."""

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
        skill_context: str = "",
    ) -> dict[str, Any]:
        """Execute the full BPA analysis pipeline.

        Args:
            prompt: User's positioning request
            tenant_id: Tenant identifier
            user_role: User's RBAC role
            config: Execution config (candidate_count, etc.)
            previous_outputs: Upstream node outputs from orchestrator
            wf1_context: WF1 Brand Discovery data from Django
            skill_context: Optional skill injection from orchestrator

        Returns:
            Complete positioning strategy result dict.
        """
        start_ms = time.time()

        candidate_count = min(config.get("candidate_count", 3), 7)
        map_count = min(config.get("perceptual_maps", 3), 5)

        # Merge WF1 context with previous_outputs
        context = self._merge_context(wf1_context, previous_outputs)

        # Phase 1: Research (gather intelligence)
        research = await self._phase_research(prompt, tenant_id, context, skill_context)

        # Phase 2: Synthesis (generate positioning)
        if not self._llm:
            return self._stub_result(prompt, start_ms)

        synthesis = await self._phase_synthesis(
            prompt,
            tenant_id,
            context,
            research,
            candidate_count,
            map_count,
            skill_context,
        )

        # Phase 3: Persist + Escalation check
        await self._phase_persist(tenant_id, synthesis)

        elapsed_ms = int((time.time() - start_ms) * 1000)

        return {
            "query": prompt,
            "recommended_positioning": synthesis.get("recommended_positioning", {}),
            "alternative_positions": synthesis.get("alternative_positions", []),
            "positioning_candidates": synthesis.get("positioning_candidates", []),
            "canvas": synthesis.get("canvas", {}),
            "perceptual_maps": synthesis.get("perceptual_maps", []),
            "differentiation": synthesis.get("differentiation", {}),
            "strategy": synthesis.get("strategy", {}),
            "confidence_score": synthesis.get("confidence_score", 0.0),
            "wf1_context_used": bool(wf1_context),
            "execution_time_ms": elapsed_ms,
            "findings": synthesis.get("findings", []),
            "recommendations": synthesis.get("recommendations", []),
            "sources": synthesis.get("sources", []),
        }

    def _merge_context(
        self,
        wf1_context: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge WF1 context and previous_outputs into unified context."""
        merged = {}

        # WF1 context (from Django endpoint)
        if wf1_context:
            merged["mra"] = wf1_context.get("mra", {})
            merged["cia"] = wf1_context.get("cia", {})
            merged["apa"] = wf1_context.get("apa", {})
            merged["tcia"] = wf1_context.get("tcia", {})
            merged["voca"] = wf1_context.get("voca", {})

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

        return merged

    async def _phase_research(
        self,
        prompt: str,
        tenant_id: str,
        context: dict[str, Any],
        skill_context: str,
    ) -> dict[str, Any]:
        """Phase 1: Research — gather competitive, audience, trend data."""
        research = {
            "competitive_landscape": self._extract_competitive(context),
            "audience_needs": self._extract_audience_needs(context),
            "trend_signals": self._extract_trends(context),
            "brand_identity": {},
            "prior_positioning": {},
        }
        return research

    def _extract_competitive(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract competitive intelligence from CIA data."""
        cia = context.get("cia", {})
        return {
            "competitors": cia.get("competitors_analyzed", [])
            or cia.get("competitors", []),
            "positioning_gaps": cia.get("positioning_gaps", []),
            "swot": cia.get("swot_analysis", {}),
            "market_positions": cia.get("market_positions", []),
        }

    def _extract_audience_needs(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract audience needs from APA + VoCA data."""
        apa = context.get("apa", {})
        voca = context.get("voca", {})
        return {
            "personas": apa.get("personas", []),
            "pain_points": (
                voca.get("pain_point_priority_matrix", {}).get("pain_points", [])
            ),
            "themes": voca.get("themes", {}).get("themes", []),
            "sentiment": voca.get("sentiment", {}),
        }

    def _extract_trends(self, context: dict[str, Any]) -> dict[str, Any]:
        """Extract trend signals from TCIA data."""
        tcia = context.get("tcia", {})
        return {
            "scored_trends": tcia.get("scored_trends", []),
            "cultural_shifts": tcia.get("cultural_shifts", []),
            "opportunity_alerts": tcia.get("opportunity_alerts", []),
        }

    async def _phase_synthesis(
        self,
        prompt: str,
        tenant_id: str,
        context: dict[str, Any],
        research: dict[str, Any],
        candidate_count: int,
        map_count: int,
        skill_context: str,
    ) -> dict[str, Any]:
        """Phase 2: Synthesis — generate positioning via Claude."""
        # Build comprehensive prompt for Claude
        if self._prompt_loader:
            from app.prompts.fallbacks import FALLBACK_POSITIONING

            system_prompt = await self._prompt_loader.load(
                "zorven-wf2-bpa-positioning",
                tenant_id=tenant_id or None,
                fallback=FALLBACK_POSITIONING,
            )
            if skill_context:
                system_prompt += f"\n\nAdditional context:\n{skill_context}"
        else:
            system_prompt = self._build_system_prompt(skill_context)
        user_prompt = self._build_user_prompt(
            prompt, context, research, candidate_count, map_count
        )

        result = await self._llm.generate_json(system_prompt, user_prompt)

        # Extract and structure the response
        candidates = result.get("positioning_candidates", [])
        recommended = result.get("recommended_positioning", {})
        if not recommended and candidates:
            # Pick the highest-scored candidate
            recommended = max(
                candidates,
                key=lambda c: c.get("scores", {}).get("overall", 0),
                default={},
            )

        alternatives = [c for c in candidates if c != recommended]

        return {
            "recommended_positioning": recommended,
            "alternative_positions": alternatives[:2],
            "positioning_candidates": candidates,
            "canvas": result.get("canvas", {}),
            "perceptual_maps": result.get("perceptual_maps", []),
            "differentiation": result.get("differentiation", {}),
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
        """Build the system prompt for Claude positioning analysis."""
        base = (
            "You are a brand positioning strategist AI. Generate comprehensive "
            "brand positioning strategies using established frameworks.\n\n"
            "Respond with valid JSON containing these top-level keys:\n"
            "- positioning_candidates: array of positioning statement objects\n"
            "- recommended_positioning: the best positioning statement\n"
            "- canvas: Value Proposition Canvas object\n"
            "- perceptual_maps: array of perceptual map objects\n"
            "- differentiation: differentiation framework object\n"
            "- strategy: full strategy document object\n"
            "- confidence_score: float 0-1\n"
            "- findings: array of key findings strings\n"
            "- recommendations: array of strategic recommendation strings\n"
            "- sources: array of data source reference objects\n\n"
            "Each positioning statement must include:\n"
            "- statement, framework_used, framework_rationale\n"
            "- target_audience, need, category, key_benefit, reason_to_believe\n"
            "- scores: {clarity, differentiation, believability, memorability, "
            "overall} (0-100)\n"
            "- data_citations: list of evidence citations\n\n"
            "Frameworks: classic, blue_ocean, jtbd, category_creation, "
            "challenger\n\n"
            "Each perceptual map must include:\n"
            "- map_id, dimension_x, dimension_y\n"
            "- entities: [{name, x, y, is_brand, is_target}]\n"
            "- migration_vector: {from_x, from_y, to_x, to_y}\n"
            "- white_space_highlighted: [{x, y, radius, label}]\n"
            "- differentiation_potential_score: 0-100\n"
            "- is_primary_recommended: boolean\n\n"
            "Differentiation must include:\n"
            "- pops, pods, rtbs, proof_points, competitive_vulnerabilities\n"
            "- overall_differentiation_score: 0-100\n\n"
            "Canvas must include:\n"
            "- customer_profile: {jobs, pains, gains}\n"
            "- value_map: {products, pain_relievers, gain_creators}\n"
            "- fit_score: 0-100\n"
            "- fit_analysis: string\n"
        )
        if skill_context:
            base += f"\n\nAdditional context:\n{skill_context}"
        return base

    def _build_user_prompt(
        self,
        prompt: str,
        context: dict[str, Any],
        research: dict[str, Any],
        candidate_count: int,
        map_count: int,
    ) -> str:
        """Build the user prompt with all research context."""
        import json

        sections = [f"Brand Positioning Request: {prompt}\n"]

        sections.append(f"Generate {candidate_count} positioning candidates.")
        sections.append(f"Generate {map_count} perceptual maps.\n")

        if research.get("competitive_landscape", {}).get("competitors"):
            sections.append(
                "## Competitive Landscape\n"
                + json.dumps(research["competitive_landscape"], indent=2, default=str)[
                    :3000
                ]
            )

        if research.get("audience_needs", {}).get("personas"):
            sections.append(
                "## Audience Needs\n"
                + json.dumps(research["audience_needs"], indent=2, default=str)[:3000]
            )

        if research.get("trend_signals", {}).get("scored_trends"):
            sections.append(
                "## Trend Signals\n"
                + json.dumps(research["trend_signals"], indent=2, default=str)[:2000]
            )

        # Market context from MRA
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
            "recommended_positioning": {
                "statement": "Stub positioning — LLM unavailable",
                "framework_used": "classic",
                "framework_rationale": "Default framework",
                "target_audience": "",
                "need": "",
                "category": "",
                "key_benefit": "",
                "reason_to_believe": "",
                "scores": {
                    "clarity": 0,
                    "differentiation": 0,
                    "believability": 0,
                    "memorability": 0,
                    "overall": 0,
                },
                "data_citations": [],
            },
            "alternative_positions": [],
            "positioning_candidates": [],
            "canvas": {},
            "perceptual_maps": [],
            "differentiation": {},
            "strategy": {},
            "confidence_score": 0.0,
            "wf1_context_used": False,
            "execution_time_ms": elapsed_ms,
            "findings": ["LLM unavailable — stub response returned"],
            "recommendations": [],
            "sources": [],
        }
