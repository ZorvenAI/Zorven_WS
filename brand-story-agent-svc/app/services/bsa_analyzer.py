"""BSA Analyzer — 5-phase PAOR engine for brand story & narrative synthesis."""

import json
import logging
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.logic.audience_emotional_synthesizer import AudienceEmotionalSynthesizer
from app.logic.brand_narrative_synthesizer import BrandNarrativeSynthesizer
from app.logic.channel_narrative_adapter import ChannelNarrativeAdapter
from app.logic.competitor_narrative_mapper import CompetitorNarrativeMapper
from app.logic.cultural_narrative_scanner import CulturalNarrativeScanner
from app.logic.elevator_pitch_generator import ElevatorPitchGenerator
from app.logic.existing_narrative_analyzer import ExistingNarrativeAnalyzer
from app.logic.human_escalation import HumanEscalation
from app.logic.mission_vision_refiner import MissionVisionRefiner
from app.logic.origin_story_crafter import OriginStoryCrafter
from app.logic.story_persister import StoryPersister
from app.logic.story_style_guide_builder import StoryStyleGuideBuilder
from app.logic.subbrand_story_variation import SubBrandStoryVariation
from app.logic.wf2_strategy_context_loader import WF2StrategyContextLoader
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.anthropic_client import AnthropicClient
from app.services.gcs_client import GCSClient

logger = logging.getLogger(__name__)


class BSAAnalyzer:
    """Five-phase PAOR engine: Research → Generate → Synthesize → Validate → Persist."""

    def __init__(
        self,
        anthropic_client: AnthropicClient | None,
        event_emitter: EventEmitter,
        gcs_client: GCSClient | None = None,
        redis_manager: RedisManager | None = None,
        prompt_loader: Any = None,
    ):
        self._llm = anthropic_client
        self._events = event_emitter
        self._prompt_loader = prompt_loader
        # Skills
        self._wf2_context = WF2StrategyContextLoader()
        self._audience_emotional = AudienceEmotionalSynthesizer()
        self._cultural_narrative = CulturalNarrativeScanner()
        self._existing_narrative = ExistingNarrativeAnalyzer()
        self._competitor_narrative = CompetitorNarrativeMapper()
        self._origin_story = OriginStoryCrafter()
        self._mission_vision = MissionVisionRefiner()
        self._pitch_generator = ElevatorPitchGenerator()
        self._channel_adapter = ChannelNarrativeAdapter()
        self._style_guide = StoryStyleGuideBuilder()
        self._subbrand = SubBrandStoryVariation()
        self._synthesizer = BrandNarrativeSynthesizer()
        self._persister = StoryPersister(gcs_client, redis_manager)
        self._escalation = HumanEscalation()

    async def analyze(
        self,
        prompt: str,
        tenant_id: str,
        user_role: str,
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        wf1_context: dict[str, Any] | None,
        bpa_context: dict[str, Any] | None,
        bpv_context: dict[str, Any] | None,
        nta_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
        baa_context: dict[str, Any] | None = None,
        job_id: str = "",
    ) -> dict[str, Any]:
        """Run full brand story & narrative analysis."""
        start_time = time.time()

        # Merge all context sources
        context = self._merge_context(
            wf1_context,
            bpa_context,
            bpv_context,
            nta_context,
            company_context,
            baa_context,
            previous_outputs,
        )

        wf1_used = any(k in context for k in ("mra", "cia", "apa", "tcia", "voca"))
        bpa_used = "bpa" in context
        bpv_used = "bpv" in context
        baa_used = "baa" in context
        nta_used = "nta" in context

        if not self._llm:
            return self._stub_result(
                prompt, start_time, wf1_used, bpa_used, bpv_used, baa_used, nta_used
            )

        # ── Phase 1: Research ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "research"},
        )

        wf2_strategy = await self._wf2_context.load(context)
        audience_emotional = await self._audience_emotional.synthesize(
            context.get("apa", {}),
            context.get("voca", {}),
            context.get("bpv", {}),
        )
        cultural_narrative = await self._cultural_narrative.scan(
            context.get("tcia", {}),
        )
        existing_narrative = await self._existing_narrative.analyze(
            context.get("company", {}),
            context.get("bpa", {}),
            context.get("bpv", {}),
        )
        competitor_narrative = await self._competitor_narrative.map(
            context.get("cia", {}),
        )

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "research"},
        )

        # ── Phase 2: Narrative Generation (Claude call 1) ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "narrative_generation"},
        )

        if self._prompt_loader:
            from app.prompts.fallbacks import FALLBACK_ORIGIN

            origin_system = await self._prompt_loader.load(
                "zorven-wf2-bsa-origin",
                tenant_id=tenant_id or None,
                fallback=FALLBACK_ORIGIN,
            )
        else:
            origin_system = self._origin_story.build_system_prompt()
        origin_user = self._origin_story.build_user_prompt(
            prompt,
            context,
            wf2_strategy,
            audience_emotional,
            existing_narrative,
            competitor_narrative,
        )
        mission_section = self._mission_vision.build_prompt_section(
            context,
            wf2_strategy,
        )
        pitch_section = self._pitch_generator.build_prompt_section(
            context,
            wf2_strategy,
        )

        # Combine into single generation prompt
        generation_user_prompt = (
            f"{origin_user}\n\n"
            f"## ADDITIONAL SECTIONS\n\n"
            f"{mission_section}\n\n"
            f"{pitch_section}\n\n"
            f"Respond with a JSON object containing: origin_story, mission_vision, pitches, "
            f"findings, recommendations, sources, confidence_score"
        )

        generation_result = await self._llm.generate_json(
            origin_system, generation_user_prompt
        )

        origin_story = generation_result.get("origin_story", {})
        mission_vision = generation_result.get("mission_vision", {})
        pitches = generation_result.get("pitches", {})
        findings = generation_result.get("findings", [])
        recommendations = generation_result.get("recommendations", [])
        sources = generation_result.get("sources", [])

        await self._events.emit(
            EventType.NARRATIVES_GENERATED,
            tenant_id,
            job_id,
            {"artifacts": ["origin_story", "mission_vision", "pitches"]},
        )

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "narrative_generation"},
        )

        # ── Phase 3: Narrative Synthesis (Claude call 2) ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "narrative_synthesis"},
        )

        channel_section = self._channel_adapter.build_prompt_section(
            context,
            origin_story,
            mission_vision,
        )
        style_section = self._style_guide.build_prompt_section(
            context,
            origin_story,
            mission_vision,
        )
        subbrand_section = self._subbrand.build_prompt_section(
            context.get("baa", {}),
            origin_story,
        )

        if self._prompt_loader:
            from app.prompts.fallbacks import FALLBACK_NARRATIVE

            synthesis_system = await self._prompt_loader.load(
                "zorven-wf2-bsa-narrative",
                tenant_id=tenant_id or None,
                fallback=FALLBACK_NARRATIVE,
            )
        else:
            synthesis_system = self._synthesizer.build_system_prompt()
        synthesis_user_prompt = (
            f"## BRAND NARRATIVE CONTEXT\n\n"
            f"Origin story: {_fmt(origin_story)}\n"
            f"Mission/Vision: {_fmt(mission_vision)}\n"
            f"Pitches: {_fmt(pitches)}\n\n"
            f"## CHANNEL ADAPTATION\n\n{channel_section}\n\n"
            f"## STYLE GUIDE\n\n{style_section}\n\n"
            f"## SUB-BRAND VARIATIONS\n\n{subbrand_section}\n\n"
            f"Respond with a JSON object containing: channel_narratives, "
            f"story_style_guide, subbrand_stories, narrative_package, "
            f"wf2_strategy_summary, findings, recommendations, confidence_score"
        )

        synthesis_result = await self._llm.generate_json(
            synthesis_system, synthesis_user_prompt
        )

        channel_narratives = synthesis_result.get("channel_narratives", {})
        story_style_guide = synthesis_result.get("story_style_guide", {})
        subbrand_stories = synthesis_result.get("subbrand_stories", [])
        narrative_package = synthesis_result.get("narrative_package", {})
        wf2_strategy_summary = synthesis_result.get("wf2_strategy_summary", {})

        findings.extend(synthesis_result.get("findings", []))
        recommendations.extend(synthesis_result.get("recommendations", []))
        sources.extend(synthesis_result.get("sources", []))

        confidence = synthesis_result.get(
            "confidence_score",
            generation_result.get("confidence_score", 0.0),
        )

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "narrative_synthesis"},
        )

        # ── Phase 4: Validation ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "validation"},
        )

        validation_issues = self._validate_narratives(
            origin_story,
            mission_vision,
            pitches,
            channel_narratives,
        )
        if validation_issues:
            findings.extend(validation_issues)

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "validation"},
        )

        # ── Phase 5: Persist + Escalation ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "persist"},
        )

        await self._persister.persist(
            tenant_id,
            job_id,
            {
                "origin_story": origin_story,
                "mission_vision": mission_vision,
                "pitches": pitches,
                "channel_narratives": channel_narratives,
                "story_style_guide": story_style_guide,
                "subbrand_stories": subbrand_stories,
                "narrative_package": narrative_package,
            },
        )

        escalation = await self._escalation.evaluate(confidence, {})
        if escalation.get("escalation_needed"):
            await self._events.emit(
                EventType.ESCALATION_TRIGGERED,
                tenant_id,
                job_id,
                escalation,
            )

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "all"},
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        return {
            "query": prompt,
            "origin_story": origin_story,
            "mission_vision": mission_vision,
            "pitches": pitches,
            "channel_narratives": channel_narratives,
            "story_style_guide": story_style_guide,
            "subbrand_stories": subbrand_stories,
            "narrative_package": narrative_package,
            "wf2_strategy_summary": wf2_strategy_summary,
            "confidence_score": confidence,
            "findings": findings,
            "recommendations": recommendations,
            "sources": sources,
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "bpv_context_used": bpv_used,
            "baa_context_used": baa_used,
            "nta_context_used": nta_used,
            "gcs_uri": "",
            "execution_time_ms": elapsed_ms,
        }

    def _merge_context(
        self,
        wf1_context: dict | None,
        bpa_context: dict | None,
        bpv_context: dict | None,
        nta_context: dict | None,
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

        # BPV
        if bpv_context:
            ctx["bpv"] = bpv_context
        if previous_outputs.get("brand_personality"):
            ctx["bpv"] = previous_outputs["brand_personality"]

        # BAA
        if baa_context:
            ctx["baa"] = baa_context
        if previous_outputs.get("brand_architecture"):
            ctx["baa"] = previous_outputs["brand_architecture"]

        # NTA
        if nta_context:
            ctx["nta"] = nta_context
        if previous_outputs.get("brand_naming"):
            ctx["nta"] = previous_outputs["brand_naming"]

        # Company
        ctx["company"] = company_context or {}

        return ctx

    def _validate_narratives(
        self,
        origin_story: dict,
        mission_vision: dict,
        pitches: dict,
        channel_narratives: dict,
    ) -> list[str]:
        """Validate narrative outputs for consistency and completeness."""
        issues = []

        # Check origin story versions exist
        versions = origin_story.get("versions", [])
        if isinstance(versions, list) and len(versions) < 3:
            issues.append(
                f"Origin story has {len(versions)} versions (expected 3: short/medium/long)"
            )

        # Check mission/vision present
        if not mission_vision.get("mission"):
            issues.append("Mission statement missing from output")
        if not mission_vision.get("vision"):
            issues.append("Vision statement missing from output")

        # Check pitches
        for duration in ["pitch_15s", "pitch_30s", "pitch_60s"]:
            if not pitches.get(duration, {}).get("content"):
                issues.append(f"Elevator pitch {duration} missing")

        return issues

    def _stub_result(
        self,
        prompt: str,
        start_time: float,
        wf1_used: bool,
        bpa_used: bool,
        bpv_used: bool,
        baa_used: bool,
        nta_used: bool,
    ) -> dict[str, Any]:
        """Return stub when LLM is unavailable."""
        return {
            "query": prompt,
            "origin_story": {},
            "mission_vision": {},
            "pitches": {},
            "channel_narratives": {},
            "story_style_guide": {},
            "subbrand_stories": [],
            "narrative_package": {},
            "wf2_strategy_summary": {},
            "confidence_score": 0.0,
            "findings": ["LLM unavailable — narrative analysis requires Claude"],
            "recommendations": [],
            "sources": [],
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "bpv_context_used": bpv_used,
            "baa_context_used": baa_used,
            "nta_context_used": nta_used,
            "gcs_uri": "",
            "execution_time_ms": int((time.time() - start_time) * 1000),
        }


def _fmt(data: dict) -> str:
    """Format dict as compact string for prompt injection."""
    return json.dumps(data, indent=None, default=str)[:3000]
