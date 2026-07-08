"""
Competitor Analyzer - Skill-based PAOR engine using Claude.

Implements the Plan-Act-Observe-Reflect reasoning loop for competitive intelligence:
  1. PLAN    - Claude decomposes query into a skill execution sequence
  2. ACT     - Execute skills per plan (with circuit breakers + RBAC)
  3. OBSERVE - Compile skill results into structured context
  4. REFLECT - Synthesize findings via Claude

Phase 1: Returns stub data. Real skill execution wired in Phase 2-4.
"""

import json
import logging
import uuid
from typing import Any, Optional

from app.api.schemas import (
    CompetitorIntelligenceResponse,
    CompetitorProfile,
    SourceItem,
)
from app.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerOpen
from app.events.catalog import EventCatalog, EventEmitter
from app.logic.guardrails import (
    GuardrailResult,
    InputGuardrails,
    OutputGuardrails,
    PlanToolGuardrails,
)
from app.rbac.engine import RBACEngine
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

_PLAN_SYSTEM_PROMPT = """\
You are a competitive intelligence planning assistant. Given an analysis query, \
decompose it into a sequence of skill invocations for competitor profiling.

Available skills (use only these IDs):
{available_skills}

Respond with a JSON object containing:
- "skill_sequence": list of skill IDs to invoke in order
- "search_queries": list of 2-4 specific competitor search queries that MUST include \
the geographic scope (city, region, country) if the user specified one. \
For example, if the user says "competitors in Pittsburgh", ALL search queries must \
include "Pittsburgh" or "Pittsburgh area" to ensure locally-scoped results.
- "max_competitors": number of competitors to discover (default 10, max 20)
- "focus_areas": list of key areas to analyze
- "analysis_type": one of "full_benchmark", "quick_scan", "swot_focus", "positioning"
- "industry": the industry/sector being analyzed
- "geography": geographic scope extracted from the query (e.g. "Pittsburgh, PA", \
"United States", "Europe"). If the user mentions a specific city, region, or country, \
extract it here. This is CRITICAL for scoping the competitive analysis to the correct market.

Only output valid JSON, no other text."""

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior competitive intelligence analyst. Synthesize the provided competitor \
data into a structured competitive intelligence report.

You must respond with a JSON object containing:
- "executive_summary": string - 2-3 paragraph executive summary of competitive landscape
- "competitor_matrix": object mapping dimension names to objects of competitor scores, e.g. \
{"pricing": {"Acme": 8, "Beta": 6}, "features": {"Acme": 7, "Beta": 9}}
- "swot_analyses": list of per-competitor SWOT objects, each with "competitor" (name), \
"strengths" (list of strings), "weaknesses" (list of strings), \
"opportunities" (list of strings), "threats" (list of strings)
- "positioning_gaps": list of objects with "dimension", "gap_description", \
"opportunity_score" (0-10), "evidence"
- "benchmarking_report": object with "summary" (string, 1-2 paragraph benchmarking overview), \
"rankings" (list of objects with "competitor", "overall_score" 0-100, "tier" one of \
"leader"/"challenger"/"niche"/"emerging"), \
"key_differentiators" (list of strings describing what sets top competitors apart), \
"market_dynamics" (string describing competitive dynamics and trends)
- "findings": list of 5-10 key finding strings (factual, data-backed)
- "recommendations": list of 3-5 strategic recommendation strings
- "confidence": float 0.0-1.0
- "methodology": list of strings describing methodology used

Only output valid JSON, no other text."""


class CompetitorAnalyzer:
    """Skill-based PAOR competitive intelligence engine."""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        rbac_engine: RBACEngine,
        circuit_breakers: dict[str, CircuitBreaker],
        input_guardrails: InputGuardrails,
        plan_guardrails: PlanToolGuardrails,
        output_guardrails: OutputGuardrails,
        event_emitter: EventEmitter,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-5",
        max_tokens: int = 4096,
        prompt_loader: Any = None,
    ) -> None:
        self.skill_registry = skill_registry
        self.rbac_engine = rbac_engine
        self.circuit_breakers = circuit_breakers
        self.input_guardrails = input_guardrails
        self.plan_guardrails = plan_guardrails
        self.output_guardrails = output_guardrails
        self.events = event_emitter
        self._anthropic_client = anthropic_client
        self._prompt_loader = prompt_loader
        self.model = model
        self.max_tokens = max_tokens
        self._session_tokens = 0

    async def analyze(
        self,
        prompt: str,
        config: dict[str, Any],
        tenant_id: str,
        user_role: str = "EDITOR",
        previous_outputs: dict[str, Any] | None = None,
    ) -> CompetitorIntelligenceResponse:
        """
        Execute the full PAOR competitive intelligence loop.

        1. PLAN    - Decompose query into skill sequence via Claude
        2. ACT     - Execute skills with RBAC + circuit breakers
        3. OBSERVE - Compile results
        4. REFLECT - Synthesize via Claude
        """
        previous_outputs = previous_outputs or {}
        session_id = str(uuid.uuid4())
        self._session_tokens = 0

        # EVT-001: Session started
        await self.events.emit(
            EventCatalog.SESSION_STARTED,
            tenant_id,
            session_id,
            {"prompt": prompt[:200], "user_role": user_role},
        )

        # Extract MRA previous outputs for enriched analysis
        mra_output = previous_outputs.get("market_research", {})
        if mra_output:
            logger.info("MRA previous outputs available - enriched analysis mode")
        else:
            logger.info("No MRA previous outputs - standalone mode")

        # Merge any skill context
        skill_context_text = config.get("skill_context", "")

        # -- L1 INPUT GUARDRAILS --
        guard_result = await self.input_guardrails.evaluate(prompt, tenant_id)
        if guard_result.blocked:
            await self.events.emit(
                EventCatalog.GUARDRAIL_INPUT,
                tenant_id,
                session_id,
                {
                    "rule_id": guard_result.rule_id,
                    "message": guard_result.message,
                },
                outcome="BLOCKED",
            )
            return CompetitorIntelligenceResponse(
                query=prompt,
                executive_summary=f"Request blocked: {guard_result.message}",
                confidence_score=0.0,
            )

        sanitized_prompt = guard_result.sanitized_prompt or prompt

        # EVT-002: Input received
        await self.events.emit(
            EventCatalog.INPUT_RECEIVED,
            tenant_id,
            session_id,
            {"prompt_length": len(sanitized_prompt)},
        )

        # -- PLAN -- Claude decomposes query into skill sequence
        logger.info("PLAN phase starting for: %s", sanitized_prompt[:100])
        available_skill_ids = self.rbac_engine.get_allowed_skills(user_role)
        plan = await self._plan_analysis(
            sanitized_prompt, available_skill_ids, skill_context_text, mra_output,
            tenant_id=tenant_id,
        )

        # EVT-004: Plan created
        await self.events.emit(
            EventCatalog.PLAN_CREATED,
            tenant_id,
            session_id,
            {
                "skill_sequence": plan.get("skill_sequence", []),
                "analysis_type": plan.get("analysis_type", "full_benchmark"),
            },
        )

        # -- L2 PLAN GUARDRAILS --
        skill_sequence = plan.get("skill_sequence", [])
        if not skill_sequence:
            skill_sequence = ["SKL-CIA-01", "SKL-CIA-08", "SKL-CIA-10"]

        plan_guard = await self.plan_guardrails.check_plan(skill_sequence)
        if plan_guard.blocked:
            await self.events.emit(
                EventCatalog.GUARDRAIL_INPUT,
                tenant_id,
                session_id,
                {"rule_id": plan_guard.rule_id, "message": plan_guard.message},
                outcome="BLOCKED",
            )
            return CompetitorIntelligenceResponse(
                query=prompt,
                executive_summary=f"Plan blocked: {plan_guard.message}",
                confidence_score=0.0,
            )

        # -- ACT -- Execute skills per plan
        logger.info("ACT phase starting - %d skills to execute", len(skill_sequence))
        skill_context = SkillContext(
            session_id=session_id,
            tenant_id=tenant_id,
            user_role=user_role,
            skill_context_text=skill_context_text,
            config=config,
        )

        skill_results: dict[str, SkillResult] = {}
        for skill_id in skill_sequence:
            # L2 per-tool guardrail
            tool_guard = await self.plan_guardrails.check_tool_call(
                skill_id, user_role, self._session_tokens
            )
            if tool_guard.blocked:
                logger.info(
                    "Skill %s blocked by guardrail: %s",
                    skill_id,
                    tool_guard.message,
                )
                continue

            skill = self.skill_registry.get_skill(skill_id)
            if skill is None:
                logger.warning("Skill %s not found in registry", skill_id)
                continue

            # EVT-005: Tool called
            await self.events.emit(
                EventCatalog.TOOL_CALLED,
                tenant_id,
                session_id,
                {"skill_id": skill_id, "skill_name": skill.meta.name},
            )

            # Build input data based on skill type
            input_data = self._build_skill_input(
                skill_id,
                plan,
                sanitized_prompt,
                skill_results,
                mra_output,
                previous_outputs,
            )

            # Execute with circuit breaker
            result = await self._execute_skill_with_circuit_breaker(
                skill, input_data, skill_context
            )

            # Track tokens
            self._session_tokens += result.tokens_used

            if result.success:
                await self.events.emit(
                    EventCatalog.TOOL_COMPLETED,
                    tenant_id,
                    session_id,
                    {
                        "skill_id": skill_id,
                        "duration_ms": result.duration_ms,
                        "tokens_used": result.tokens_used,
                    },
                )
            else:
                await self.events.emit(
                    EventCatalog.TOOL_FAILED,
                    tenant_id,
                    session_id,
                    {
                        "skill_id": skill_id,
                        "error": result.error,
                        "duration_ms": result.duration_ms,
                    },
                    outcome="FAILURE",
                )

            skill_results[skill_id] = result
            skill_context.previous_skill_results[skill_id] = result.data

        logger.info(
            "ACT phase complete: %d/%d skills succeeded",
            sum(1 for r in skill_results.values() if r.success),
            len(skill_results),
        )

        # -- OBSERVE -- Compile results
        raw_context, sources = self._compile_skill_results(skill_results)

        # -- REFLECT -- Synthesize via Claude
        synthesis_allowed = self.rbac_engine.check_permission("SKL-CIA-10", user_role)
        if synthesis_allowed.decision == "ALLOW":
            logger.info("REFLECT phase starting - synthesizing findings")
            synthesis = await self._synthesize(
                sanitized_prompt, raw_context, skill_context_text, mra_output,
                tenant_id=tenant_id,
            )
        else:
            logger.info("REFLECT phase skipped - role %s denied SKL-CIA-10", user_role)
            synthesis = {
                "executive_summary": raw_context[:500] if raw_context else "",
                "findings": [
                    r.data.get("summary", "")
                    for r in skill_results.values()
                    if r.success and r.data.get("summary")
                ],
                "recommendations": [],
                "confidence": 0.4,
                "methodology": [
                    "LLM synthesis skipped (insufficient role permissions)"
                ],
            }

        # Build competitor profiles from skill results
        competitors = self._extract_competitor_profiles(skill_results)
        competitors_analyzed = [c.name for c in competitors if c.name]
        skills_used = [sid for sid, r in skill_results.items() if r.success]

        # Extract SWOT analyses: prefer synthesis output, fall back to skill results
        swot_analyses = synthesis.get("swot_analyses", [])
        if not swot_analyses:
            swot_data = skill_results.get("SKL-CIA-08")
            if swot_data and swot_data.success:
                swot_analyses = swot_data.data.get("swot_analyses", [])
        # Also populate from competitor profile SWOT data if still empty
        if not swot_analyses:
            swot_analyses = [
                {"competitor": c.name, **c.swot} for c in competitors if c.swot
            ]

        # Extract benchmarking report: prefer synthesis, fall back to skill
        benchmarking_report = synthesis.get("benchmarking_report", {})
        if not benchmarking_report:
            bench_data = skill_results.get("SKL-CIA-10")
            if bench_data and bench_data.success:
                benchmarking_report = bench_data.data.get("report", {})
                if isinstance(benchmarking_report, str):
                    benchmarking_report = {"summary": benchmarking_report}

        # Extract positioning gaps: prefer synthesis, fall back to skill
        positioning_gaps = synthesis.get("positioning_gaps", [])
        if not positioning_gaps:
            gap_data = skill_results.get("SKL-CIA-09")
            if gap_data and gap_data.success:
                positioning_gaps = gap_data.data.get("positioning_gaps", [])

        response = CompetitorIntelligenceResponse(
            query=prompt,
            executive_summary=synthesis.get("executive_summary", ""),
            competitors=competitors,
            competitors_analyzed=competitors_analyzed,
            competitor_matrix=synthesis.get("competitor_matrix", {}),
            swot_analyses=swot_analyses,
            positioning_gaps=positioning_gaps,
            positioning_map=synthesis.get("positioning_map", {}),
            benchmarking_report=benchmarking_report,
            sources=sources,
            findings=synthesis.get("findings", []),
            recommendations=synthesis.get("recommendations", []),
            raw_context=raw_context[:50000],
            confidence_score=float(synthesis.get("confidence", 0.5)),
            methodology_notes=synthesis.get("methodology", [])
            + [f"Skills used: {', '.join(skills_used)}"],
        )

        # -- L3 OUTPUT GUARDRAILS --
        output_guard = await self.output_guardrails.evaluate(
            response, list(skill_results.values()), tenant_id
        )

        if output_guard.blocked:
            await self.events.emit(
                EventCatalog.GUARDRAIL_OUTPUT,
                tenant_id,
                session_id,
                {"rule_id": output_guard.rule_id},
                outcome="BLOCKED",
            )

        # EVT-009: Response sent
        await self.events.emit(
            EventCatalog.RESPONSE_SENT,
            tenant_id,
            session_id,
            {
                "competitors_count": len(response.competitors),
                "sources_count": len(response.sources),
                "findings_count": len(response.findings),
                "confidence": response.confidence_score,
                "skills_used": skills_used,
            },
        )

        # EVT-011: Session completed
        await self.events.emit(
            EventCatalog.SESSION_COMPLETED,
            tenant_id,
            session_id,
            {"total_tokens": self._session_tokens},
        )

        return response

    async def close(self) -> None:
        """Clean up resources."""
        if self._anthropic_client is not None:
            try:
                await self._anthropic_client.close()
            except Exception:
                pass
            self._anthropic_client = None

    # -- PLAN phase --

    async def _plan_analysis(
        self,
        prompt: str,
        available_skill_ids: list[str],
        skill_context: str = "",
        mra_output: dict[str, Any] | None = None,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Use Claude to decompose the query into a skill plan."""
        skill_descriptions = []
        for sid in available_skill_ids:
            skill = self.skill_registry.get_skill(sid)
            if skill:
                skill_descriptions.append(
                    f"- {sid} ({skill.meta.name}): {skill.meta.description}"
                )

        default_plan = {
            "skill_sequence": ["SKL-CIA-01", "SKL-CIA-08", "SKL-CIA-10"],
            "search_queries": [prompt],
            "max_competitors": 10,
            "focus_areas": ["competitive_landscape"],
            "analysis_type": "full_benchmark",
            "industry": "",
            "geography": "",
        }

        if self._anthropic_client is None:
            logger.info("No Anthropic client - using default analysis plan")
            return default_plan

        try:
            skills_text = "\n".join(skill_descriptions)
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_PLANNING

                system = await self._prompt_loader.load(
                    "zorven-wf1-cia-planning",
                    tenant_id=tenant_id or None,
                    variables={
                        "available_skills": skills_text,
                        "context.available_skills": skills_text,
                    },
                    fallback=FALLBACK_PLANNING,
                )
            else:
                system = _PLAN_SYSTEM_PROMPT.format(
                    available_skills=skills_text
                )
            if skill_context:
                system += f"\n\nAdditional context:\n{skill_context[:2000]}"
            if mra_output:
                mra_summary = mra_output.get("market_overview", "")[:500]
                if mra_summary:
                    system += (
                        f"\n\nMarket research context (from upstream MRA):\n"
                        f"{mra_summary}"
                    )

            message = await self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )

            tokens_used = getattr(message, "usage", None)
            if tokens_used:
                self._session_tokens += getattr(
                    tokens_used, "input_tokens", 0
                ) + getattr(tokens_used, "output_tokens", 0)

            content = message.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            plan = json.loads(content)

            # Ensure skill_sequence only contains available skills
            plan["skill_sequence"] = [
                s for s in plan.get("skill_sequence", []) if s in available_skill_ids
            ]
            if not plan["skill_sequence"]:
                plan["skill_sequence"] = [
                    s
                    for s in default_plan["skill_sequence"]
                    if s in available_skill_ids
                ]

            return plan
        except Exception as exc:
            logger.warning("Failed to plan analysis via Claude: %s", exc)
            return default_plan

    # -- ACT phase -- skill execution

    def _build_skill_input(
        self,
        skill_id: str,
        plan: dict[str, Any],
        prompt: str,
        previous_results: dict[str, SkillResult],
        mra_output: dict[str, Any] | None = None,
        previous_outputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build input data for a skill based on the plan and previous results."""
        mra_output = mra_output or {}

        if skill_id == "SKL-CIA-01":
            # Competitor Discovery - uses MRA competitive_landscape as seeds
            mra_competitors = mra_output.get("competitive_landscape", [])
            return {
                "query": prompt,
                "industry": plan.get("industry", ""),
                "geography": plan.get("geography", ""),
                "max_competitors": plan.get("max_competitors", 10),
                "mra_competitors": mra_competitors,
                "market_context": {
                    "market_overview": mra_output.get("market_overview", ""),
                    "market_size": mra_output.get("market_sizing", {}),
                    "industry_trends": mra_output.get("industry_trends", []),
                },
                "search_queries": plan.get("search_queries", [prompt]),
            }
        elif skill_id in ("SKL-CIA-02", "SKL-CIA-03", "SKL-CIA-04", "SKL-CIA-05"):
            # Per-competitor profiling skills
            discovery_data = previous_results.get(
                "SKL-CIA-01", SkillResult(skill_id="SKL-CIA-01", success=False)
            )
            return {
                "competitors": discovery_data.data.get("competitors", []),
                "prompt": prompt,
            }
        elif skill_id == "SKL-CIA-06":
            # Market Share Estimator - uses MRA's market_sizing
            discovery_data = previous_results.get(
                "SKL-CIA-01", SkillResult(skill_id="SKL-CIA-01", success=False)
            )
            return {
                "competitors": discovery_data.data.get("competitors", []),
                "industry_context": {
                    "market_sizing": mra_output.get("market_sizing", {}),
                    "findings": mra_output.get("findings", []),
                    "industry_trends": mra_output.get("industry_trends", []),
                },
            }
        elif skill_id == "SKL-CIA-07":
            # RAG Context Retrieval
            return {"query": prompt, "top_k": 5}
        elif skill_id in ("SKL-CIA-08", "SKL-CIA-09", "SKL-CIA-10"):
            # LLM analysis skills - compile all previous results
            raw_parts = []
            for sid, res in previous_results.items():
                if res.success and res.data:
                    raw_parts.append(json.dumps(res.data, default=str)[:10000])
            return {
                "raw_data": "\n\n".join(raw_parts),
                "analysis_type": plan.get("analysis_type", "full_benchmark"),
                "prompt": prompt,
                "market_context": {
                    "market_overview": mra_output.get("market_overview", ""),
                    "market_sizing": mra_output.get("market_sizing", {}),
                    "industry_trends": mra_output.get("industry_trends", []),
                    "mra_sources": mra_output.get("sources", []),
                    "mra_confidence": mra_output.get("confidence_score", 0),
                },
            }
        elif skill_id == "SKL-CIA-11":
            # Report Persister
            return {
                "prompt": prompt,
                "report_data": {
                    sid: res.data
                    for sid, res in previous_results.items()
                    if res.success
                },
            }
        elif skill_id == "SKL-CIA-12":
            # Human Escalation
            return {
                "reason": "Manual escalation requested",
                "context_summary": prompt[:500],
                "severity": "medium",
            }
        return {"prompt": prompt}

    async def _execute_skill_with_circuit_breaker(
        self,
        skill: BaseSkill,
        input_data: dict,
        context: SkillContext,
    ) -> SkillResult:
        """Execute a skill with circuit breaker protection."""
        cb_name = skill.meta.circuit_breaker_dependency
        cb = self.circuit_breakers.get(cb_name) if cb_name else None

        if cb is None:
            return await skill.execute(input_data, context)

        try:
            return await cb.call(skill.execute, input_data, context)
        except CircuitBreakerOpen as exc:
            logger.warning(
                "Circuit breaker open for %s (%s), fallback=%s",
                skill.meta.skill_id,
                cb_name,
                exc.fallback,
            )
            await self.events.emit(
                EventCatalog.CIRCUIT_BREAKER_OPENED,
                context.tenant_id,
                context.session_id,
                {
                    "dependency": cb_name,
                    "skill_id": skill.meta.skill_id,
                    "fallback": exc.fallback,
                },
                outcome="FALLBACK",
            )
            return SkillResult(
                skill_id=skill.meta.skill_id,
                success=False,
                error=f"Circuit breaker open: {cb_name}",
            )
        except Exception as exc:
            logger.warning(
                "Skill %s failed (circuit breaker recorded): %s",
                skill.meta.skill_id,
                exc,
            )
            return SkillResult(
                skill_id=skill.meta.skill_id,
                success=False,
                error=str(exc),
            )

    # -- OBSERVE phase --

    def _compile_skill_results(
        self, skill_results: dict[str, SkillResult]
    ) -> tuple[str, list[SourceItem]]:
        """Compile skill results into raw context string and source list."""
        parts: list[str] = []
        sources: list[SourceItem] = []
        seen_urls: set[str] = set()

        for skill_id, result in skill_results.items():
            if not result.success:
                continue

            data = result.data

            # Competitor Discovery (SKL-CIA-01)
            if skill_id == "SKL-CIA-01":
                competitors = data.get("competitors", [])
                if competitors:
                    parts.append("## Discovered Competitors\n")
                    for c in competitors:
                        name = c.get("name", "Unknown")
                        website = c.get("website", "")
                        parts.append(f"### {name}\nWebsite: {website}\n")
                        if website and website not in seen_urls:
                            seen_urls.add(website)
                            sources.append(
                                SourceItem(type="web", title=name, url=website)
                            )

            # Website Profiler (SKL-CIA-02)
            elif skill_id == "SKL-CIA-02":
                profiles = data.get("profiles", [])
                if profiles:
                    parts.append("## Website Profiles\n")
                    for p in profiles:
                        parts.append(
                            f"### {p.get('name', 'N/A')}\n" f"{p.get('summary', '')}\n"
                        )

            # Social Media Analyzer (SKL-CIA-03)
            elif skill_id == "SKL-CIA-03":
                social = data.get("social_data", [])
                if social:
                    parts.append("## Social Media Analysis\n")
                    for s in social:
                        parts.append(
                            f"### {s.get('name', 'N/A')}\n{s.get('summary', '')}\n"
                        )

            # Review Aggregator (SKL-CIA-04)
            elif skill_id == "SKL-CIA-04":
                reviews = data.get("reviews", [])
                if reviews:
                    parts.append("## Customer Reviews\n")
                    for r in reviews:
                        parts.append(
                            f"### {r.get('name', 'N/A')}\n{r.get('summary', '')}\n"
                        )

            # Pricing Extractor (SKL-CIA-05)
            elif skill_id == "SKL-CIA-05":
                pricing = data.get("pricing_data", [])
                if pricing:
                    parts.append("## Pricing Analysis\n")
                    for p in pricing:
                        parts.append(
                            f"### {p.get('name', 'N/A')}\n{p.get('summary', '')}\n"
                        )

            # Market Share (SKL-CIA-06)
            elif skill_id == "SKL-CIA-06":
                shares = data.get("market_shares", [])
                if shares:
                    parts.append("## Market Share Estimates\n")
                    for ms in shares:
                        parts.append(
                            f"- {ms.get('name', 'N/A')}: "
                            f"{ms.get('estimated_share_pct', 'N/A')}%\n"
                        )

            # RAG Context (SKL-CIA-07)
            elif skill_id == "SKL-CIA-07":
                chunks = data.get("chunks", [])
                if chunks:
                    parts.append("## Prior Analysis Context\n")
                    for chunk in chunks:
                        parts.append(f"- {chunk.get('content', '')[:500]}\n")

            # SWOT (SKL-CIA-08)
            elif skill_id == "SKL-CIA-08":
                swots = data.get("swot_analyses", [])
                if swots:
                    parts.append("## SWOT Analyses\n")
                    for sw in swots:
                        parts.append(f"### {sw.get('competitor', 'N/A')}\n")
                        parts.append(json.dumps(sw, default=str)[:2000] + "\n")

            # Positioning Gaps (SKL-CIA-09)
            elif skill_id == "SKL-CIA-09":
                gaps = data.get("positioning_gaps", [])
                if gaps:
                    parts.append("## Positioning Gaps\n")
                    for g in gaps:
                        parts.append(
                            f"- {g.get('dimension', 'N/A')}: "
                            f"{g.get('gap_description', '')}\n"
                        )

            # Benchmarking (SKL-CIA-10)
            elif skill_id == "SKL-CIA-10":
                report = data.get("report", "")
                if report:
                    parts.append(f"## Benchmarking Report\n{report}\n")

            # Collect any extra sources from skill data
            for src in data.get("sources", []):
                url = src.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append(
                        SourceItem(
                            type=src.get("type", "web"),
                            title=src.get("title", ""),
                            url=url,
                        )
                    )

        raw_context = "\n".join(parts)
        return raw_context, sources

    @staticmethod
    def _extract_competitor_profiles(
        skill_results: dict[str, SkillResult],
    ) -> list[CompetitorProfile]:
        """Extract structured competitor profiles from skill results."""
        discovery = skill_results.get("SKL-CIA-01")
        if not discovery or not discovery.success:
            return []

        profiles = []
        for comp in discovery.data.get("competitors", []):
            slug = comp.get("slug", comp.get("name", "").lower().replace(" ", "-"))
            profile = CompetitorProfile(
                slug=slug,
                name=comp.get("name", ""),
                website=comp.get("website", ""),
                description=comp.get("description", ""),
                market_position=comp.get("market_position", ""),
                confidence=comp.get("confidence", 0.5),
            )

            # Enrich with profiling data from other skills
            website_data = skill_results.get("SKL-CIA-02")
            if website_data and website_data.success:
                for wp in website_data.data.get("profiles", []):
                    if wp.get("slug") == slug:
                        profile.website_profile = wp

            social_data = skill_results.get("SKL-CIA-03")
            if social_data and social_data.success:
                for sd in social_data.data.get("social_data", []):
                    if sd.get("slug") == slug:
                        profile.social_presence = sd

            review_data = skill_results.get("SKL-CIA-04")
            if review_data and review_data.success:
                for rd in review_data.data.get("reviews", []):
                    if rd.get("slug") == slug:
                        profile.review_profile = rd

            pricing_data = skill_results.get("SKL-CIA-05")
            if pricing_data and pricing_data.success:
                for pd in pricing_data.data.get("pricing_data", []):
                    if pd.get("slug") == slug:
                        profile.pricing_profile = pd

            share_data = skill_results.get("SKL-CIA-06")
            if share_data and share_data.success:
                for ms in share_data.data.get("market_shares", []):
                    if ms.get("slug") == slug:
                        profile.market_share_estimate = ms

            swot_data = skill_results.get("SKL-CIA-08")
            if swot_data and swot_data.success:
                for sw in swot_data.data.get("swot_analyses", []):
                    if sw.get("slug") == slug:
                        profile.swot = sw

            profiles.append(profile)

        return profiles

    # -- REFLECT phase --

    async def _synthesize(
        self,
        prompt: str,
        raw_context: str,
        skill_context: str = "",
        mra_output: dict[str, Any] | None = None,
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Use Claude to synthesize competitive intelligence findings."""
        default_synthesis = {
            "executive_summary": f"Competitive intelligence for: {prompt}",
            "competitor_matrix": {},
            "positioning_gaps": [],
            "findings": [f"Analysis gathered for: {prompt}"],
            "recommendations": ["Review raw data for detailed insights."],
            "confidence": 0.3,
            "methodology": ["Automated web search", "Competitor profiling"],
        }

        if self._anthropic_client is None:
            logger.info("No Anthropic client - returning default synthesis")
            default_synthesis["findings"] = [
                "STUB MODE: CIA_ANTHROPIC_API_KEY is not configured "
                "on this deployment."
            ]
            return default_synthesis

        if not raw_context.strip():
            logger.warning("No raw context for synthesis")
            default_synthesis["findings"] = [
                "DATA COLLECTION FAILED: All research skills returned "
                "empty results. Check CIA_TAVILY_API_KEY."
            ]
            return default_synthesis

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_SYNTHESIS

                system = await self._prompt_loader.load(
                    "zorven-wf1-cia-synthesis",
                    tenant_id=tenant_id or None,
                    fallback=FALLBACK_SYNTHESIS,
                )
            else:
                system = _SYNTHESIS_SYSTEM_PROMPT
            if skill_context:
                system += f"\n\nAdditional methodology context:\n{skill_context[:2000]}"

            user_message = f"Competitive intelligence query: {prompt}\n\n"
            if mra_output:
                mra_summary = mra_output.get("market_overview", "")[:1000]
                if mra_summary:
                    user_message += f"Market research context:\n{mra_summary}\n\n"
            user_message += f"Raw competitive data:\n{raw_context[:30000]}"

            message = await self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            tokens_used = getattr(message, "usage", None)
            if tokens_used:
                self._session_tokens += getattr(
                    tokens_used, "input_tokens", 0
                ) + getattr(tokens_used, "output_tokens", 0)

            content = message.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            synthesis = json.loads(content)
            return synthesis
        except Exception as exc:
            logger.error(
                "Failed to synthesize via Claude (%s): %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return default_synthesis
