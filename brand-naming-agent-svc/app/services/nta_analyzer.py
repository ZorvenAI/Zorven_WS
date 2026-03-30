"""NTA Analyzer — 5-phase PAOR engine for naming & tagline generation."""

import asyncio
import logging
import time
from typing import Any

from app.logic.audience_psychology_analyzer import AudiencePsychologyAnalyzer
from app.logic.brand_context_loader import BrandContextLoader
from app.logic.competitive_naming_analyzer import CompetitiveNamingAnalyzer
from app.logic.domain_checker import DomainChecker
from app.logic.human_escalation import HumanEscalation
from app.logic.identity_seed_loader import IdentitySeedLoader
from app.logic.name_generator import NameGenerator
from app.logic.name_scorer import NameScorer
from app.logic.naming_brief_builder import NamingBriefBuilder
from app.logic.naming_persister import NamingPersister
from app.logic.rag_retriever import RAGRetriever
from app.logic.social_handle_checker import SocialHandleChecker
from app.logic.tagline_synthesizer import TaglineSynthesizer
from app.logic.trademark_searcher import TrademarkSearcher
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.anthropic_client import AnthropicClient

logger = logging.getLogger(__name__)


class NTAAnalyzer:
    """Five-phase PAOR engine: Research → Generate → Availability → Tagline → Persist."""

    def __init__(
        self,
        anthropic_client: AnthropicClient | None,
        event_emitter: EventEmitter,
    ):
        self._llm = anthropic_client
        self._events = event_emitter
        # Skills
        self._brand_context = BrandContextLoader()
        self._audience_psychology = AudiencePsychologyAnalyzer()
        self._competitive_naming = CompetitiveNamingAnalyzer()
        self._identity_seed = IdentitySeedLoader()
        self._rag = RAGRetriever()
        self._domain_checker = DomainChecker()
        self._social_checker = SocialHandleChecker()
        self._trademark_searcher = TrademarkSearcher()
        self._name_generator = NameGenerator()
        self._name_scorer = NameScorer()
        self._tagline_synthesizer = TaglineSynthesizer()
        self._brief_builder = NamingBriefBuilder()
        self._persister = NamingPersister()
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
        company_context: dict[str, Any] | None,
        baa_context: dict[str, Any] | None = None,
        job_id: str = "",
    ) -> dict[str, Any]:
        """Run full naming & tagline analysis."""
        start_time = time.time()

        # Merge all context sources
        context = self._merge_context(
            wf1_context,
            bpa_context,
            bpv_context,
            company_context,
            baa_context,
            previous_outputs,
        )

        wf1_used = any(k in context for k in ("mra", "cia", "apa", "tcia", "voca"))
        bpa_used = "bpa" in context
        bpv_used = "bpv" in context
        baa_used = "baa" in context

        if not self._llm:
            return self._stub_result(
                prompt, start_time, wf1_used, bpa_used, bpv_used, baa_used
            )

        # ── Phase 1: Research ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "research"},
        )

        brand_ctx = await self._brand_context.load(
            context.get("baa", {}),
            config,
        )
        audience_psych = await self._audience_psychology.analyze(
            context.get("apa", {}),
            context.get("voca", {}),
        )
        competitive = await self._competitive_naming.analyze(
            context.get("cia", {}),
            context.get("mra", {}),
        )
        identity_seed = await self._identity_seed.load(
            context.get("bpv", {}),
            context.get("bpa", {}),
            context.get("company", {}),
        )
        rag_docs = await self._rag.retrieve(tenant_id, prompt)

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "research"},
        )

        # ── Phase 2: Name Generation (Claude call 1) ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "name_generation"},
        )

        name_system_prompt = self._name_generator.build_system_prompt()
        name_user_prompt = self._name_generator.build_user_prompt(
            prompt,
            context,
            audience_psych,
            competitive,
            identity_seed,
            brand_ctx,
            rag_docs,
        )

        name_result = await self._llm.generate_json(
            name_system_prompt, name_user_prompt
        )

        raw_candidates = name_result.get("name_candidates", [])
        findings = name_result.get("findings", [])
        recommendations = name_result.get("recommendations", [])
        sources = name_result.get("sources", [])

        await self._events.emit(
            EventType.NAMES_GENERATED,
            tenant_id,
            job_id,
            {"candidate_count": len(raw_candidates)},
        )

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "name_generation"},
        )

        # ── Phase 3: Availability Checking ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "availability"},
        )

        availability_results = {}

        async def _check_candidate(candidate: dict) -> None:
            """Check availability for a single candidate concurrently."""
            name = candidate.get("name", "")
            if not name:
                return
            slug = name.lower().replace(" ", "").replace("-", "")

            domain_avail, social_avail, trademark_result = await asyncio.gather(
                self._domain_checker.check(slug),
                self._social_checker.check(slug),
                self._trademark_searcher.search(name),
            )

            availability_results[name] = {
                "domain": domain_avail,
                "social": social_avail,
                "trademark": trademark_result,
            }

            # Update candidate availability fields
            candidate["availability"] = {
                "domain_com": domain_avail.get(".com"),
                "domain_io": domain_avail.get(".io"),
                "domain_co": domain_avail.get(".co"),
                "twitter": social_avail.get("twitter"),
                "instagram": social_avail.get("instagram"),
                "linkedin": social_avail.get("linkedin"),
                "trademark_clear": trademark_result.get("clear"),
                "trademark_notes": trademark_result.get("notes", ""),
            }

        # Run availability checks concurrently across all candidates
        await asyncio.gather(*[_check_candidate(c) for c in raw_candidates])

        # Score candidates with availability data
        scored_candidates = self._name_scorer.score_all(raw_candidates, context)

        # Sort by overall score descending
        scored_candidates.sort(
            key=lambda c: c.get("scores", {}).get("overall", 0),
            reverse=True,
        )

        # Shortlist top N
        from app.core.config import settings

        shortlist_size = config.get("shortlist_size", settings.SHORTLIST_SIZE)
        shortlisted = scored_candidates[:shortlist_size]
        shortlisted_names = [c.get("name", "") for c in shortlisted]

        # Mark shortlisted
        for candidate in scored_candidates:
            candidate["shortlisted"] = candidate.get("name") in shortlisted_names

        # Scoring summary
        scoring_summary = self._name_scorer.summarize(scored_candidates)

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "availability", "shortlisted": shortlisted_names},
        )

        # ── Phase 4: Tagline Synthesis (Claude call 2) ──
        await self._events.emit(
            EventType.ANALYSIS_PHASE_STARTED,
            tenant_id,
            job_id,
            {"phase": "tagline_synthesis"},
        )

        tagline_system_prompt = self._tagline_synthesizer.build_system_prompt()
        tagline_user_prompt = self._tagline_synthesizer.build_user_prompt(
            prompt,
            shortlisted,
            context,
            identity_seed,
        )

        tagline_result = await self._llm.generate_json(
            tagline_system_prompt, tagline_user_prompt
        )

        taglines = tagline_result.get("taglines", [])
        naming_brief_data = tagline_result.get("naming_brief", {})

        # Build final naming brief
        naming_brief = self._brief_builder.build(
            naming_brief_data,
            shortlisted,
            taglines,
            context,
        )

        confidence = tagline_result.get(
            "confidence_score",
            name_result.get("confidence_score", 0.0),
        )

        # Merge findings/recommendations from tagline call
        findings.extend(tagline_result.get("findings", []))
        recommendations.extend(tagline_result.get("recommendations", []))
        sources.extend(tagline_result.get("sources", []))

        await self._events.emit(
            EventType.ANALYSIS_PHASE_COMPLETED,
            tenant_id,
            job_id,
            {"phase": "tagline_synthesis", "tagline_count": len(taglines)},
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
            {
                "name_candidates": scored_candidates,
                "shortlisted_names": shortlisted_names,
                "taglines": taglines,
                "naming_brief": naming_brief,
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
            "name_candidates": scored_candidates,
            "shortlisted_names": shortlisted_names,
            "taglines": taglines,
            "naming_brief": naming_brief,
            "availability_results": availability_results,
            "scoring_summary": scoring_summary,
            "confidence_score": confidence,
            "findings": findings,
            "recommendations": recommendations,
            "sources": sources,
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "bpv_context_used": bpv_used,
            "baa_context_used": baa_used,
            "execution_time_ms": elapsed_ms,
        }

    def _merge_context(
        self,
        wf1_context: dict | None,
        bpa_context: dict | None,
        bpv_context: dict | None,
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

        # Company
        ctx["company"] = company_context or {}

        return ctx

    def _stub_result(
        self,
        prompt: str,
        start_time: float,
        wf1_used: bool,
        bpa_used: bool,
        bpv_used: bool,
        baa_used: bool,
    ) -> dict[str, Any]:
        """Return stub when LLM is unavailable."""
        return {
            "query": prompt,
            "name_candidates": [],
            "shortlisted_names": [],
            "taglines": [],
            "naming_brief": {},
            "availability_results": {},
            "scoring_summary": {},
            "confidence_score": 0.0,
            "findings": ["LLM unavailable — naming analysis requires Claude"],
            "recommendations": [],
            "sources": [],
            "wf1_context_used": wf1_used,
            "bpa_context_used": bpa_used,
            "bpv_context_used": bpv_used,
            "baa_context_used": baa_used,
            "execution_time_ms": int((time.time() - start_time) * 1000),
        }


def _fmt(data: dict) -> str:
    """Format dict as compact string for prompt injection."""
    import json

    return json.dumps(data, indent=None, default=str)[:3000]
