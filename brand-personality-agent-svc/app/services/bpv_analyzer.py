"""BPV Analyzer — 3-phase PAOR engine for personality design."""

import logging
import time
from typing import Any

from app.logic.aaker_profiler import AakerProfiler
from app.logic.archetype_selector import ArchetypeSelector
from app.logic.audience_psychology_analyzer import AudiencePsychologyAnalyzer
from app.logic.brand_perception_analyzer import BrandPerceptionAnalyzer
from app.logic.character_brief_synthesizer import CharacterBriefSynthesizer
from app.logic.emotional_attribute_mapper import EmotionalAttributeMapper
from app.logic.human_escalation import HumanEscalation
from app.logic.identity_values_seed_loader import IdentityValuesSeedLoader
from app.logic.personality_persister import PersonalityPersister
from app.logic.rag_retriever import RAGRetriever
from app.logic.sub_brand_constraint import SubBrandConstraint
from app.logic.values_hierarchy_builder import ValuesHierarchyBuilder
from app.logic.voice_matrix_designer import VoiceMatrixDesigner
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)

# The 12 Jungian archetypes for the system prompt
JUNGIAN_ARCHETYPES = [
    "Innocent", "Sage", "Explorer", "Outlaw", "Magician", "Hero",
    "Lover", "Jester", "Regular Guy", "Caregiver", "Ruler", "Creator",
]


class BPVAnalyzer:
    """Three-phase PAOR engine: Research → Design → Persist."""

    def __init__(
        self,
        anthropic_client: AnthropicClient | None,
        event_emitter: EventEmitter,
    ):
        self._llm = anthropic_client
        self._events = event_emitter
        # Skills
        self._audience_psychology = AudiencePsychologyAnalyzer()
        self._brand_perception = BrandPerceptionAnalyzer()
        self._identity_seed = IdentityValuesSeedLoader()
        self._rag = RAGRetriever()
        self._aaker = AakerProfiler()
        self._archetype = ArchetypeSelector()
        self._values = ValuesHierarchyBuilder()
        self._emotional = EmotionalAttributeMapper()
        self._voice = VoiceMatrixDesigner()
        self._character = CharacterBriefSynthesizer()
        self._persister = PersonalityPersister()
        self._escalation = HumanEscalation()
        self._sub_brand = SubBrandConstraint()

    async def analyze(
        self,
        prompt: str,
        tenant_id: str,
        user_role: str,
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        wf1_context: dict[str, Any] | None,
        bpa_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
        baa_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run full personality analysis."""
        start_time = time.time()

        # Merge all context sources
        context = self._merge_context(
            wf1_context, bpa_context, company_context,
            baa_context, previous_outputs,
        )

        wf1_used = "mra" in context or "cia" in context
        bpa_used = "bpa" in context
        baa_used = "baa" in context

        if not self._llm:
            return self._stub_result(
                prompt, start_time, wf1_used, bpa_used, baa_used
            )

        # ── Phase 1: Research ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED, tenant_id, "",
            {"phase": "research"},
        )

        audience_psych = await self._audience_psychology.analyze(
            context.get("apa", {}), context.get("voca", {}),
        )
        brand_perception = await self._brand_perception.analyze(
            context.get("voca", {}), context.get("tcia", {}),
        )
        identity_seed = await self._identity_seed.load(
            context.get("company", {}),
            context.get("bpa", {}),
            context.get("baa", {}),
        )
        rag_docs = await self._rag.retrieve(tenant_id, prompt)

        # ── Phase 2: Personality Design (via Claude) ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED, tenant_id, "",
            {"phase": "design"},
        )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            prompt, context, audience_psych, brand_perception,
            identity_seed, rag_docs,
        )

        llm_result = await self._llm.generate_json(system_prompt, user_prompt)

        # Validate/normalize outputs using skill modules
        aaker_profile = await self._aaker.validate(
            llm_result.get("aaker_profile", {})
        )
        archetype = await self._archetype.validate(
            llm_result.get("archetype", {})
        )
        values_hierarchy = await self._values.validate(
            llm_result.get("values_hierarchy", {})
        )
        emotional_map = await self._emotional.validate(
            llm_result.get("emotional_map", {})
        )
        voice_matrix = await self._voice.validate(
            llm_result.get("voice_matrix", {})
        )
        character_brief = await self._character.validate(
            llm_result.get("character_brief", {}),
            context.get("bpa", {}),
        )

        # PG-07: Sub-brand Aaker deviation constraint
        brand_context_id = self._get_brand_context_id(
            previous_outputs, config
        )
        sub_brand_applied = False
        sub_brand_violations = []

        if brand_context_id != "parent":
            # Load parent personality from previous_outputs or context
            parent_personality = previous_outputs.get(
                "brand_personality", {}
            )
            if parent_personality and parent_personality.get("aaker_profile"):
                constraint_result = await self._sub_brand.validate(
                    parent_personality, {"aaker_profile": aaker_profile},
                )
                adjusted = constraint_result.get("adjusted_personality", {})
                if adjusted.get("aaker_profile"):
                    aaker_profile = adjusted["aaker_profile"]
                sub_brand_violations = constraint_result.get(
                    "violations", []
                )
                sub_brand_applied = True

        confidence = llm_result.get("confidence_score", 0.0)
        findings = llm_result.get("findings", [])
        recommendations = llm_result.get("recommendations", [])
        sources = llm_result.get("sources", [])

        if sub_brand_violations:
            for v in sub_brand_violations:
                findings.append(
                    f"PG-07: {v['dimension']} adjusted from "
                    f"{v['original_score']} to {v['adjusted_score']} "
                    f"(parent: {v['parent_score']}, max deviation: ±20)"
                )

        # ── Phase 3: Persist + Escalation ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED, tenant_id, "",
            {"phase": "persist"},
        )

        persist_result = await self._persister.persist(tenant_id, {
            "aaker_profile": aaker_profile,
            "archetype": archetype,
            "values_hierarchy": values_hierarchy,
        })

        # Sync personality context to Django
        await self._persister.sync_personality_context(
            tenant_id,
            {
                "aaker_profile": aaker_profile,
                "archetype": archetype,
                "values_hierarchy": values_hierarchy,
            },
            brand_context_id=brand_context_id,
        )

        escalation = await self._escalation.evaluate(confidence, {})

        if escalation.get("escalation_needed"):
            await self._events.emit(
                EventType.ESCALATION_TRIGGERED, tenant_id, "",
                escalation,
            )

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED, tenant_id, "",
            {"phase": "all"},
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "query": prompt,
            "aaker_profile": aaker_profile,
            "archetype": archetype,
            "values_hierarchy": values_hierarchy,
            "emotional_map": emotional_map,
            "voice_matrix": voice_matrix,
            "character_brief": character_brief,
            "confidence_score": confidence,
            "findings": findings,
            "recommendations": recommendations,
            "sources": sources,
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "baa_context_used": baa_used,
            "execution_time_ms": elapsed_ms,
            "sub_brand_constraint_applied": sub_brand_applied,
        }

    def _merge_context(
        self,
        wf1_context: dict | None,
        bpa_context: dict | None,
        company_context: dict | None,
        baa_context: dict | None,
        previous_outputs: dict | None,
    ) -> dict[str, Any]:
        """Merge all context sources. previous_outputs takes precedence."""
        previous_outputs = previous_outputs or {}
        ctx: dict[str, Any] = {}

        # WF1 agents
        if wf1_context:
            ctx["mra"] = wf1_context.get("mra", {})
            ctx["cia"] = wf1_context.get("cia", {})
            ctx["apa"] = wf1_context.get("apa", {})
            ctx["tcia"] = wf1_context.get("tcia", {})
            ctx["voca"] = wf1_context.get("voca", {})

        # Override with previous_outputs
        if previous_outputs.get("market_research"):
            ctx["mra"] = previous_outputs["market_research"]
        if previous_outputs.get("competitor_intelligence"):
            ctx["cia"] = previous_outputs["competitor_intelligence"]
        if previous_outputs.get("audience_persona"):
            ctx["apa"] = previous_outputs["audience_persona"]
        if previous_outputs.get("trend_cultural"):
            ctx["tcia"] = previous_outputs["trend_cultural"]
        if previous_outputs.get("voice_of_customer"):
            ctx["voca"] = previous_outputs["voice_of_customer"]

        # BPA
        if bpa_context:
            ctx["bpa"] = bpa_context
        if previous_outputs.get("brand_positioning"):
            ctx["bpa"] = previous_outputs["brand_positioning"]

        # BAA
        if baa_context:
            ctx["baa"] = baa_context
        if previous_outputs.get("brand_architecture"):
            ctx["baa"] = previous_outputs["brand_architecture"]

        # Company
        ctx["company"] = company_context or {}

        return ctx

    def _build_system_prompt(self) -> str:
        """Build system prompt for personality design."""
        return (
            "You are a Brand Personality & Values strategist. "
            "You design brand personalities using the Aaker 5-Dimension "
            "framework and Jungian archetypes.\n\n"
            "## Aaker 5 Dimensions (each 0-100)\n"
            "1. Sincerity (honest, wholesome, cheerful, down-to-earth)\n"
            "2. Excitement (daring, spirited, imaginative, up-to-date)\n"
            "3. Competence (reliable, intelligent, successful, leader)\n"
            "4. Sophistication (upper-class, charming, glamorous)\n"
            "5. Ruggedness (outdoorsy, tough, strong, rugged)\n\n"
            "## 12 Jungian Archetypes\n"
            + "\n".join(f"- {a}" for a in JUNGIAN_ARCHETYPES)
            + "\n\n"
            "## Required Output (JSON)\n"
            "Return a JSON object with these keys:\n"
            "- aaker_profile: {dimensions: [{dimension, score, rationale}], "
            "primary_dimension, secondary_dimension, "
            "differentiation_score}\n"
            "- archetype: {primary: {name, core_desire, fear, strategy, "
            "gift, shadow, brand_expression}, secondary: {same}, "
            "resonance_score, blend_rationale}\n"
            "- values_hierarchy: {core: [{name, definition, "
            "behavioral_manifestation}], supporting: [same], "
            "aspirational: [same], authenticity_score}\n"
            "- emotional_map: {personas: [{persona, emotions: [{emotion, "
            "intensity}]}], consistency_score}\n"
            "- voice_matrix: {tone_spectrum: [{dimension, low_end, "
            "high_end, position}], vocabulary: {preferred: [], "
            "avoided: []}, style: {sentence_length, formality, "
            "perspective}, humor: {type, frequency}, "
            "dos: [], donts: [], channel_adaptations: [{channel, "
            "adaptation}]}\n"
            "- character_brief: {persona_card: {name, age, personality, "
            "values, communication_style, visual_identity}, "
            "executive_summary, positioning_alignment_score}\n"
            "- confidence_score: 0.0-1.0\n"
            "- findings: []\n"
            "- recommendations: []\n"
            "- sources: []\n\n"
            "Core values: 3-5. Supporting values: 3-5. "
            "Aspirational values: 1-3.\n"
            "All scores on 0-100 scale unless specified."
        )

    def _build_user_prompt(
        self,
        prompt: str,
        context: dict,
        audience_psych: dict,
        brand_perception: dict,
        identity_seed: dict,
        rag_docs: dict,
    ) -> str:
        """Build user prompt with all context."""
        parts = [f"Brand personality request: {prompt}\n"]

        if identity_seed:
            parts.append(f"## Identity Seed\n{_fmt(identity_seed)}\n")
        if audience_psych:
            parts.append(f"## Audience Psychology\n{_fmt(audience_psych)}\n")
        if brand_perception:
            parts.append(f"## Brand Perception\n{_fmt(brand_perception)}\n")
        if context.get("company"):
            parts.append(f"## Company\n{_fmt(context['company'])}\n")
        if context.get("bpa"):
            parts.append(f"## Brand Positioning\n{_fmt(context['bpa'])}\n")
        if context.get("baa"):
            parts.append(f"## Brand Architecture\n{_fmt(context['baa'])}\n")

        return "\n".join(parts)

    def _get_brand_context_id(
        self, previous_outputs: dict, config: dict
    ) -> str:
        """Extract brand_context_id from config or context."""
        brand_ctx = config.get("brand_context_id", "")
        if not brand_ctx:
            brand_ctx = previous_outputs.get(
                "brand_context_id", "parent"
            )
        return brand_ctx or "parent"

    def _stub_result(
        self,
        prompt: str,
        start_time: float,
        wf1_used: bool,
        bpa_used: bool,
        baa_used: bool,
    ) -> dict[str, Any]:
        """Return stub when LLM is unavailable."""
        return {
            "query": prompt,
            "aaker_profile": {},
            "archetype": {},
            "values_hierarchy": {},
            "emotional_map": {},
            "voice_matrix": {},
            "character_brief": {},
            "confidence_score": 0.0,
            "findings": ["LLM unavailable — personality analysis requires Claude"],
            "recommendations": [],
            "sources": [],
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "baa_context_used": baa_used,
            "execution_time_ms": int((time.time() - start_time) * 1000),
            "sub_brand_constraint_applied": False,
        }


def _fmt(data: dict) -> str:
    """Format dict as compact string for prompt injection."""
    import json
    return json.dumps(data, indent=None, default=str)[:3000]
