"""CAA Analyzer — 5-phase PAOR engine for campaign architecture synthesis.

Phase 1: Research (no LLM) — strategy context, benchmarks, competitor ads,
         Odoo customer data, RAG learnings + input guardrails
Phase 2: Architecture Synthesis (Claude call 1) — funnel mapping,
         audience targeting, placement/budget
Phase 3: Blueprint Synthesis (Claude call 2) — A/B test plan,
         full blueprint assembly
Phase 4: Validation — budget totals, targeting completeness, Meta enums
Phase 5: Persist + Escalation — Redis + GCS, human escalation
"""

import logging
import time
from typing import Any

from app.cache.redis_manager import RedisManager
from app.logic.ab_test_planner import ABTestPlanner
from app.logic.audience_targeting_builder import AudienceTargetingBuilder
from app.logic.blueprint_synthesizer import BlueprintSynthesizer
from app.logic.competitor_ad_analyzer import CompetitorAdAnalyzer
from app.logic.funnel_objective_mapper import FunnelObjectiveMapper
from app.logic.guardrails import InputGuardrails, OutputGuardrails, PlanGuardrails
from app.logic.human_escalation import HumanEscalation
from app.logic.market_benchmark_researcher import MarketBenchmarkResearcher
from app.logic.odoo_customer_loader import OdooCustomerLoader
from app.logic.placement_budget_builder import PlacementBudgetBuilder
from app.logic.rag_intelligence_retriever import RAGIntelligenceRetriever
from app.logic.strategy_context_loader import StrategyContextLoader
from app.messaging.event_emitter import EventEmitter, EventType
from app.services.anthropic_client import AnthropicClient
from app.services.gcs_client import GCSClient
from app.services.tavily_client import TavilyClient

logger = logging.getLogger(__name__)


class CAAAnalyzer:
    """Five-phase PAOR engine for campaign architecture."""

    def __init__(
        self,
        anthropic_client: AnthropicClient | None,
        event_emitter: EventEmitter,
        gcs_client: GCSClient | None = None,
        redis_manager: RedisManager | None = None,
        tavily_client: TavilyClient | None = None,
    ):
        self._llm = anthropic_client
        self._events = event_emitter
        self._gcs = gcs_client
        self._redis = redis_manager
        self._tavily = tavily_client

        # Research skills
        self._strategy_ctx = StrategyContextLoader()
        self._benchmark = MarketBenchmarkResearcher()
        self._competitor = CompetitorAdAnalyzer()
        self._odoo_loader = OdooCustomerLoader()
        self._rag_retriever = RAGIntelligenceRetriever()

        # Synthesis skills (prompt builders)
        self._funnel_mapper = FunnelObjectiveMapper()
        self._audience_builder = AudienceTargetingBuilder()
        self._placement_builder = PlacementBudgetBuilder()
        self._test_planner = ABTestPlanner()
        self._blueprint_synth = BlueprintSynthesizer()

        # Escalation
        self._escalation = HumanEscalation()

        # Guardrails
        self._input_guards = InputGuardrails()
        self._plan_guards = PlanGuardrails()
        self._output_guards = OutputGuardrails()

    async def analyze(
        self,
        prompt: str,
        tenant_id: str,
        user_role: str = "VIEWER",
        config: dict[str, Any] | None = None,
        previous_outputs: dict[str, Any] | None = None,
        wf1_context: dict[str, Any] | None = None,
        bpa_context: dict[str, Any] | None = None,
        wf2_chain_context: dict[str, Any] | None = None,
        company_context: dict[str, Any] | None = None,
        baa_context: dict[str, Any] | None = None,
        odoo_context: dict[str, Any] | None = None,
        rag_context: dict[str, Any] | None = None,
        tavily_benchmarks: dict[str, Any] | None = None,
        tavily_competitors: dict[str, Any] | None = None,
        job_id: str = "",
    ) -> dict[str, Any]:
        """Run 5-phase campaign architecture analysis."""
        config = config or {}
        previous_outputs = previous_outputs or {}
        start_time = time.time()

        # Extract budget from input
        budget = float(config.get("daily_budget", 0) or 0)
        if not budget:
            budget = float(
                config.get("budget", 0) or previous_outputs.get("budget", 0) or 100.0
            )

        await self._events.emit(
            EventType.ARCHITECTURE_SYNTHESIS_STARTED, tenant_id, job_id
        )

        # ── Phase 1: Research (no LLM) ──
        logger.info("Phase 1: Research — building strategy context")

        # SKL-CAA-01: Strategy context
        strategy_ctx = self._strategy_ctx.build_context(
            wf1_context=wf1_context,
            bpa_context=bpa_context,
            wf2_chain_context=wf2_chain_context,
            company_context=company_context,
            baa_context=baa_context,
            odoo_context=odoo_context,
            rag_context=rag_context,
        )

        # SKL-CAA-02: Benchmarks
        benchmark_data = self._benchmark.process(
            tavily_benchmarks or {}, strategy_ctx.get("industry", "")
        )

        # SKL-CAA-03: Competitor ads
        cia_data = strategy_ctx.get("competitor_intelligence", {})
        competitor_data = self._competitor.process(tavily_competitors or {}, cia_data)

        # SKL-CAA-04: Odoo customers
        customer_data = self._odoo_loader.process(odoo_context)

        # SKL-CAA-05: RAG learnings
        rag_intelligence = self._rag_retriever.process(rag_context)

        # Input guardrails
        budget_check = self._input_guards.check_budget_sanity(budget)
        special_ad_cat = self._input_guards.detect_special_ad_category(
            company_context, prompt
        )
        if special_ad_cat != "NONE":
            await self._events.emit(
                EventType.SPECIAL_AD_CATEGORY_DETECTED,
                tenant_id,
                job_id,
                {"category": special_ad_cat},
            )
        if not budget_check["valid"]:
            await self._events.emit(
                EventType.BUDGET_GUARDRAIL_TRIGGERED,
                tenant_id,
                job_id,
                {"issues": budget_check["issues"]},
            )

        # ── Phase 2: Architecture Synthesis (Claude call 1) ──
        logger.info("Phase 2: Architecture Synthesis — Claude call 1")

        # Build prompt sections from skills
        funnel_section = self._funnel_mapper.build_prompt_section(strategy_ctx, budget)
        audience_section = self._audience_builder.build_prompt_section(
            strategy_ctx, customer_data
        )
        placement_section = self._placement_builder.build_prompt_section(
            strategy_ctx, budget, benchmark_data
        )

        call1_system = (
            "You are a Meta Ads campaign architect. Analyze the provided "
            "brand and market context to design the campaign's funnel "
            "strategy, audience targeting, and placement/budget allocation.\n\n"
            "Output a single JSON object with keys: funnel_map, "
            "targeting_specs, placement_budget, kpi_targets.\n\n"
            "Return ONLY valid JSON, no markdown or commentary."
        )
        call1_user = (
            f"# Campaign Architecture Request\n\n"
            f"User request: {prompt}\n\n"
            f"Company: {strategy_ctx.get('company_name', 'Unknown')}\n"
            f"Industry: {strategy_ctx.get('industry', 'Unknown')}\n"
            f"Brand maturity: {strategy_ctx.get('brand_maturity', 'new')}\n"
            f"Daily budget: ${budget:.2f}\n"
            f"Special Ad Category: {special_ad_cat}\n\n"
            f"{funnel_section}\n"
            f"{audience_section}\n"
            f"{placement_section}\n"
            f"{self._benchmark.build_prompt_section(benchmark_data)}\n"
            f"{self._competitor.build_prompt_section(competitor_data)}\n"
            f"{self._odoo_loader.build_prompt_section(customer_data)}\n"
            f"{self._rag_retriever.build_prompt_section(rag_intelligence)}\n"
        )

        call1_result = {}
        if self._llm:
            try:
                call1_result = await self._llm.generate_json(call1_system, call1_user)
            except Exception as exc:
                logger.error("Claude call 1 failed: %s", exc)
                call1_result = {}

        # Plan guardrails on call 1 output — defensive type checks
        # Claude may return unexpected types (list vs dict)
        funnel_map = call1_result.get("funnel_map", {})
        if not isinstance(funnel_map, dict):
            funnel_map = {}
        targeting_specs = call1_result.get("targeting_specs", [])
        if not isinstance(targeting_specs, list):
            targeting_specs = [targeting_specs] if targeting_specs else []
        kpi_targets = call1_result.get("kpi_targets", {})
        if not isinstance(kpi_targets, dict):
            kpi_targets = {}

        guardrail_warnings = []
        budget_alloc = self._plan_guards.check_budget_allocation(funnel_map)
        if not budget_alloc["valid"]:
            guardrail_warnings.append(budget_alloc.get("issue", ""))

        overlap = self._plan_guards.check_audience_overlap(targeting_specs)
        if not overlap["valid"]:
            for ov in overlap.get("overlaps", []):
                guardrail_warnings.append(
                    f"Audience overlap {ov['overlap_pct']}% " f"between {ov['ad_sets']}"
                )

        kpi_check = self._plan_guards.check_kpi_realism(kpi_targets, benchmark_data)
        if not kpi_check["valid"]:
            guardrail_warnings.extend(kpi_check.get("issues", []))

        await self._events.emit(
            EventType.ARCHITECTURE_SYNTHESIS_COMPLETED, tenant_id, job_id
        )

        # ── Phase 3: Blueprint Synthesis (Claude call 2) ──
        logger.info("Phase 3: Blueprint Synthesis — Claude call 2")

        test_section = self._test_planner.build_prompt_section(
            strategy_ctx, budget, benchmark_data
        )
        benchmark_section = self._benchmark.build_prompt_section(benchmark_data)
        competitor_section = self._competitor.build_prompt_section(competitor_data)

        call2_system = self._blueprint_synth.build_system_prompt()
        call2_user = self._blueprint_synth.build_user_prompt(
            call1_result=call1_result,
            test_plan_section=test_section,
            benchmark_section=benchmark_section,
            competitor_section=competitor_section,
            budget=budget,
            company_name=strategy_ctx.get("company_name", ""),
        )

        call2_result = {}
        if self._llm:
            try:
                call2_result = await self._llm.generate_json(call2_system, call2_user)
            except Exception as exc:
                logger.error("Claude call 2 failed: %s", exc)
                call2_result = {}

        await self._events.emit(
            EventType.BLUEPRINT_SYNTHESIS_COMPLETED, tenant_id, job_id
        )

        # ── Phase 4: Validation ──
        logger.info("Phase 4: Validation")

        blueprint = call2_result.get("blueprint", {})
        if not isinstance(blueprint, dict):
            blueprint = {}
        meta_check = self._output_guards.check_meta_api_schema(blueprint)
        budget_cap_check = self._output_guards.check_budget_cap(blueprint)

        if not budget_cap_check["valid"]:
            guardrail_warnings.append(budget_cap_check.get("issue", ""))

        # Test sample size guard
        test_plan = call2_result.get("test_plan", {})
        if not isinstance(test_plan, dict):
            test_plan = {}
        test_check = self._plan_guards.check_test_sample_size(test_plan, budget)
        if not test_check["valid"]:
            guardrail_warnings.extend(test_check.get("issues", []))

        # ── Phase 5: Escalation check ──
        confidence = call2_result.get("confidence_score", 0.0)
        escalation = self._escalation.check(call2_result, benchmark_data)
        if escalation["should_escalate"]:
            await self._events.emit(
                EventType.ESCALATION_TRIGGERED,
                tenant_id,
                job_id,
                {"reasons": escalation["reasons"]},
            )

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Build findings
        findings = []
        if guardrail_warnings:
            findings.extend(guardrail_warnings)
        if escalation["should_escalate"]:
            findings.extend([f"ESCALATION: {r}" for r in escalation["reasons"]])

        # Log key data for debugging
        logger.info(
            "Call 1 keys: %s, Call 2 keys: %s",
            list(call1_result.keys())[:10],
            list(call2_result.keys())[:10],
        )
        bp = call2_result.get("blueprint", {})
        logger.info(
            "Blueprint type=%s, has_name=%s, ad_sets=%d, funnel_stages=%d",
            type(bp).__name__,
            bool(bp.get("campaign_name") if isinstance(bp, dict) else False),
            len(bp.get("ad_sets", []) if isinstance(bp, dict) else []),
            len(funnel_map.get("stages", []) if isinstance(funnel_map, dict) else []),
        )

        # Assemble result
        result = {
            "query": prompt,
            "blueprint": call2_result.get("blueprint", {}),
            "funnel_map": call2_result.get("funnel_map", funnel_map),
            "targeting_specs": call2_result.get("targeting_specs", targeting_specs),
            "placement_budget": call2_result.get(
                "placement_budget", call1_result.get("placement_budget", {})
            ),
            "test_plan": test_plan,
            "kpi_targets": call2_result.get("kpi_targets", kpi_targets),
            "performance_projections": call2_result.get("performance_projections", {}),
            "risk_assessment": call2_result.get("risk_assessment", {}),
            "creative_briefs": call2_result.get("creative_briefs", []),
            "special_ad_category": special_ad_cat,
            "meta_api_compatible": meta_check.get("meta_api_compatible", False),
            "confidence_score": confidence,
            "findings": findings,
            "recommendations": call2_result.get("recommendations", []),
            "sources": (
                benchmark_data.get("tavily_sources", [])
                + competitor_data.get("sources", [])
            ),
            "wf1_context_used": bool(wf1_context),
            "wf2_context_used": bool(wf2_chain_context),
            "bpa_context_used": bool(bpa_context),
            "company_context_used": bool(company_context),
            "tavily_benchmarks_used": bool(tavily_benchmarks),
            "odoo_data_used": customer_data.get("available", False),
            "rag_learnings_used": rag_intelligence.get("available", False),
            "gcs_uri": "",
            "execution_time_ms": elapsed_ms,
        }

        return result
