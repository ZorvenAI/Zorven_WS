"""
Market Researcher — Skill-based PAOR engine using Claude.

Implements the Plan-Act-Observe-Reflect reasoning loop with 8 executable skills:
  1. PLAN    — Claude decomposes query into a skill execution sequence
  2. ACT     — Execute skills per plan (with circuit breakers + RBAC)
  3. OBSERVE — Compile skill results into structured context
  4. REFLECT — Synthesize findings via Claude
"""

import json
import logging
import uuid
from typing import Any, Optional

from app.api.schemas import MarketResearchResponse, SourceItem
from app.circuit_breaker.breaker import CircuitBreaker, CircuitBreakerOpen
from app.events.catalog import EventCatalog, EventEmitter
from app.logic.guardrails import (
    GuardrailResult,
    InputGuardrails,
    OutputGuardrails,
    PlanToolGuardrails,
)
from app.rbac.engine import RBACEngine
from app.services.api_clients import GNewsClient, TavilySearchClient, WorldBankClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

_PLAN_SYSTEM_PROMPT = """\
You are a market research planning assistant. Given a research query, decompose it \
into a sequence of skill invocations and data gathering tasks.

IMPORTANT — Geographic Scope Detection:
If the user specifies a geographic area (city, town, county, state, region, or country), \
you MUST scope ALL search queries to that area. For local queries, prefer web search \
over economic indicators (World Bank data is country-level only).

Available skills (use only these IDs):
{available_skills}

Respond with a JSON object containing:
- "skill_sequence": list of skill IDs to invoke in order (e.g. ["SKL-MRA-01", "SKL-MRA-04", "SKL-MRA-03"])
- "search_queries": list of 2-4 specific web search queries (include location if specified)
- "indicators": list of economic indicator names (options: gdp, gdp_growth, inflation, \
unemployment, population, gni_per_capita, trade_pct_gdp, fdi_net_inflows). \
Use EMPTY list [] for local/city-level queries.
- "news_queries": list of 1-2 news search queries
- "countries": list of ISO country codes (default ["WLD"])
- "geographic_scope": one of "local", "national", "regional", "global"
- "scope_location": the specific location mentioned
- "focus_areas": list of key areas to analyze
- "analysis_type": one of "landscape", "sizing", "segmentation", "trends"

Only output valid JSON, no other text."""

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior market research analyst. Synthesize the provided raw data into a \
structured market research report.

CRITICAL — Geographic Scope:
If the research query specifies a geographic area, scope your entire analysis to that area.

You must respond with a JSON object containing:
- "overview": string — A comprehensive 2-3 paragraph market overview
- "sizing": object — Market sizing with keys "tam", "sam", "som". Each value must be \
an object with "value" (string) and "description" (string)
- "competitors": list of objects with "name", "description", "market_position"
- "trends": list of 3-7 key industry trend strings
- "findings": list of 5-10 key finding strings (factual, data-backed)
- "recommendations": list of 3-5 actionable recommendation strings
- "confidence": float 0.0-1.0
- "methodology": list of strings describing methodology used

Only output valid JSON, no other text."""


class MarketResearcher:
    """Skill-based PAOR market research engine."""

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
        max_tokens: int = 32768,
        prompt_loader: Any = None,
        # Legacy clients for backward-compatible data compilation
        tavily_client: Optional[TavilySearchClient] = None,
        world_bank_client: Optional[WorldBankClient] = None,
        news_client: Optional[GNewsClient] = None,
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

    async def research(
        self,
        prompt: str,
        config: dict[str, Any],
        tenant_id: str,
        user_role: str = "EDITOR",
        previous_outputs: dict[str, Any] | None = None,
    ) -> MarketResearchResponse:
        """
        Execute the full PAOR market research loop with skill system.

        1. PLAN    — Decompose query into skill sequence via Claude
        2. ACT     — Execute skills with RBAC + circuit breakers
        3. OBSERVE — Compile results
        4. REFLECT — Synthesize via Claude
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

        # Merge any skill context or config hints
        focus = config.get("focus", "")
        skill_context_text = config.get("skill_context", "")
        augmented_prompt = prompt
        if focus:
            augmented_prompt += f" (focus: {focus})"

        # ── L1 INPUT GUARDRAILS ──
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
            return MarketResearchResponse(
                query=prompt,
                market_overview=f"Request blocked: {guard_result.message}",
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

        # ── PLAN — Claude decomposes query into skill sequence ──
        logger.info("PLAN phase starting for: %s", sanitized_prompt[:100])
        available_skill_ids = self.rbac_engine.get_allowed_skills(user_role)
        plan = await self._plan_research(
            sanitized_prompt, available_skill_ids, skill_context_text,
            tenant_id=tenant_id,
        )

        # EVT-004: Plan created
        await self.events.emit(
            EventCatalog.PLAN_CREATED,
            tenant_id,
            session_id,
            {
                "skill_sequence": plan.get("skill_sequence", []),
                "analysis_type": plan.get("analysis_type", "landscape"),
            },
        )

        # ── L2 PLAN GUARDRAILS ──
        skill_sequence = plan.get("skill_sequence", [])
        if not skill_sequence:
            # Default plan: search + economic + synthesis
            skill_sequence = ["SKL-MRA-01", "SKL-MRA-04", "SKL-MRA-03"]

        plan_guard = await self.plan_guardrails.check_plan(skill_sequence)
        if plan_guard.blocked:
            await self.events.emit(
                EventCatalog.GUARDRAIL_INPUT,
                tenant_id,
                session_id,
                {"rule_id": plan_guard.rule_id, "message": plan_guard.message},
                outcome="BLOCKED",
            )
            return MarketResearchResponse(
                query=prompt,
                market_overview=f"Plan blocked: {plan_guard.message}",
                confidence_score=0.0,
            )

        # ── ACT — Execute skills per plan ──
        logger.info("ACT phase starting — %d skills to execute", len(skill_sequence))
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
                skill_id, plan, sanitized_prompt, skill_results
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
            # Make available for downstream skills
            skill_context.previous_skill_results[skill_id] = result.data

        logger.info(
            "ACT phase complete: %d/%d skills succeeded",
            sum(1 for r in skill_results.values() if r.success),
            len(skill_results),
        )

        # ── OBSERVE — Compile results ──
        raw_context, sources = self._compile_skill_results(skill_results)

        # Build geographic scope hint
        geo_scope = plan.get("geographic_scope", "")
        scope_location = plan.get("scope_location", "")
        geo_hint = ""
        if geo_scope and geo_scope != "global":
            geo_hint = f"\nGeographic scope: {geo_scope}"
            if scope_location:
                geo_hint += f" — {scope_location}"
            geo_hint += (
                "\nScope ALL analysis (TAM/SAM/SOM, competitors, overview) "
                "to this geographic area."
            )

        # ── REFLECT — Synthesize via Claude (RBAC: requires SKL-MRA-03 access) ──
        synthesis_allowed = self.rbac_engine.check_permission("SKL-MRA-03", user_role)
        if synthesis_allowed.decision == "ALLOW":
            logger.info("REFLECT phase starting — synthesizing findings")
            synthesis = await self._synthesize(
                sanitized_prompt, raw_context, skill_context_text, geo_hint,
                tenant_id=tenant_id,
            )
        else:
            logger.info("REFLECT phase skipped — role %s denied SKL-MRA-03", user_role)
            synthesis = {
                "overview": raw_context[:500] if raw_context else "",
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

        # Build response
        economic_data = self._extract_economic_data(skill_results)
        skills_used = [sid for sid, r in skill_results.items() if r.success]

        response = MarketResearchResponse(
            query=prompt,
            market_overview=synthesis.get("overview", ""),
            market_sizing=synthesis.get("sizing", {}),
            competitive_landscape=synthesis.get("competitors", []),
            industry_trends=synthesis.get("trends", []),
            economic_indicators=economic_data,
            sources=sources,
            findings=synthesis.get("findings", []),
            recommendations=synthesis.get("recommendations", []),
            raw_context=raw_context[:50000],
            confidence_score=float(synthesis.get("confidence", 0.5)),
            methodology_notes=synthesis.get("methodology", [])
            + [f"Skills used: {', '.join(skills_used)}"],
        )

        # ── L3 OUTPUT GUARDRAILS ──
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

    # ── PLAN phase ──

    async def _plan_research(
        self,
        prompt: str,
        available_skill_ids: list[str],
        skill_context: str = "",
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Use Claude to decompose the research query into a skill plan."""
        # Build skill descriptions for the planner
        skill_descriptions = []
        for sid in available_skill_ids:
            skill = self.skill_registry.get_skill(sid)
            if skill:
                skill_descriptions.append(
                    f"- {sid} ({skill.meta.name}): {skill.meta.description}"
                )

        default_plan = {
            "skill_sequence": ["SKL-MRA-01", "SKL-MRA-04", "SKL-MRA-03"],
            "search_queries": [prompt],
            "indicators": ["gdp", "gdp_growth"],
            "news_queries": [prompt],
            "countries": ["WLD"],
            "focus_areas": ["market_overview"],
            "analysis_type": "landscape",
            "geographic_scope": "global",
            "scope_location": "",
        }

        if self._anthropic_client is None:
            logger.info("No Anthropic client — using default research plan")
            return default_plan

        try:
            skills_text = "\n".join(skill_descriptions)
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_PLANNING

                system = await self._prompt_loader.load(
                    "zorven-wf1-mra-planning",
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

            message = await self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=1024,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )

            tokens_used = getattr(message, "usage", None)
            if tokens_used:
                self._session_tokens += getattr(
                    tokens_used, "input_tokens", 0
                ) + getattr(tokens_used, "output_tokens", 0)

            content = next(
                b.text for b in message.content if b.type == "text"
            ).strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            plan = json.loads(content, strict=False)

            # Ensure skill_sequence only contains available skills
            plan["skill_sequence"] = [
                s for s in plan.get("skill_sequence", []) if s in available_skill_ids
            ]
            if not plan["skill_sequence"]:
                # Fallback must also be filtered by available skills
                plan["skill_sequence"] = [
                    s
                    for s in default_plan["skill_sequence"]
                    if s in available_skill_ids
                ]

            return plan
        except Exception as exc:
            logger.warning("Failed to plan research via Claude: %s", exc)
            return default_plan

    # ── ACT phase — skill execution ──

    def _build_skill_input(
        self,
        skill_id: str,
        plan: dict[str, Any],
        prompt: str,
        previous_results: dict[str, SkillResult],
    ) -> dict[str, Any]:
        """Build input data for a skill based on the plan and previous results."""
        if skill_id == "SKL-MRA-01":
            return {
                "query": prompt,
                "focus_areas": plan.get("focus_areas", []),
                "geography": plan.get("scope_location", ""),
                "max_results": 5,
                "include_news": True,
            }
        elif skill_id == "SKL-MRA-02":
            return {
                "queries": plan.get("search_queries", [prompt]),
                "extraction_focus": plan.get("analysis_type", ""),
                "max_results": 5,
            }
        elif skill_id == "SKL-MRA-03":
            # Gather raw data from previous skill results
            raw_parts = []
            for sid, res in previous_results.items():
                if res.success and res.data:
                    raw_parts.append(json.dumps(res.data, default=str)[:10000])
            return {
                "raw_data": "\n\n".join(raw_parts),
                "analysis_type": plan.get("analysis_type", "landscape"),
                "prompt": prompt,
            }
        elif skill_id == "SKL-MRA-04":
            return {
                "country": (
                    plan.get("countries", ["WLD"])[0]
                    if plan.get("countries")
                    else "WLD"
                ),
                "indicators": plan.get("indicators", ["gdp", "gdp_growth"]),
                "period": "2019:2024",
            }
        elif skill_id == "SKL-MRA-05":
            return {"query": prompt, "top_k": 5}
        elif skill_id == "SKL-MRA-06":
            # Collect findings from synthesis skill
            synthesis_data = previous_results.get(
                "SKL-MRA-03", SkillResult(skill_id="SKL-MRA-03", success=False)
            )
            return {
                "findings": synthesis_data.data.get("findings", []),
                "analysis": synthesis_data.data.get("analysis", ""),
                "prompt": prompt,
            }
        elif skill_id == "SKL-MRA-07":
            # Index the report or raw context
            report_data = previous_results.get(
                "SKL-MRA-06", SkillResult(skill_id="SKL-MRA-06", success=False)
            )
            return {
                "content": report_data.data.get(
                    "report_text", json.dumps(plan, default=str)
                ),
                "metadata": {"query": prompt},
                "chunk_type": "research_report",
            }
        elif skill_id == "SKL-MRA-08":
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
            # EVT-012
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

    # ── OBSERVE phase ──

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

            # Web search results (SKL-MRA-01)
            if skill_id == "SKL-MRA-01":
                web_results = data.get("results", [])
                if web_results:
                    parts.append("## Web Research Results\n")
                    for r in web_results:
                        title = r.get("title", "Untitled")
                        url = r.get("url", "")
                        content = r.get("content", r.get("snippet", ""))
                        parts.append(f"### {title}\nURL: {url}\n{content}\n")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            src_type = "news" if r.get("published_at") else "web"
                            sources.append(
                                SourceItem(type=src_type, title=title, url=url)
                            )

            # Extracted data (SKL-MRA-02)
            elif skill_id == "SKL-MRA-02":
                extracted = data.get("extracted_data", [])
                if extracted:
                    parts.append("## Industry Data\n")
                    for item in extracted:
                        parts.append(
                            f"### {item.get('title', 'N/A')}\n"
                            f"{item.get('content', '')}\n"
                        )
                for src in data.get("sources", []):
                    url = src.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        sources.append(
                            SourceItem(
                                type="web",
                                title=src.get("title", ""),
                                url=url,
                            )
                        )

            # Economic data (SKL-MRA-04)
            elif skill_id == "SKL-MRA-04":
                indicators = data.get("indicators", [])
                if indicators:
                    parts.append("## Economic Indicators\n")
                    for ind in indicators:
                        parts.append(
                            f"### {ind.get('indicator_name', ind.get('indicator_id', 'N/A'))}\n"
                        )
                        for v in ind.get("values", [])[:5]:
                            parts.append(
                                f"- {v.get('date', 'N/A')}: {v.get('value', 'N/A')}\n"
                            )
                    sources.append(
                        SourceItem(
                            type="economic_data",
                            title="World Bank Open Data",
                            url="https://data.worldbank.org",
                        )
                    )

            # RAG chunks (SKL-MRA-05)
            elif skill_id == "SKL-MRA-05":
                chunks = data.get("chunks", [])
                if chunks:
                    parts.append("## RAG Context\n")
                    for chunk in chunks:
                        parts.append(f"- {chunk.get('content', '')[:500]}\n")

            # Analysis synthesis (SKL-MRA-03)
            elif skill_id == "SKL-MRA-03":
                analysis = data.get("analysis", "")
                if analysis:
                    parts.append(f"## Analysis\n{analysis}\n")

        raw_context = "\n".join(parts)
        return raw_context, sources

    @staticmethod
    def _extract_economic_data(
        skill_results: dict[str, SkillResult],
    ) -> dict[str, Any]:
        """Extract formatted economic data from skill results."""
        econ_result = skill_results.get("SKL-MRA-04")
        if not econ_result or not econ_result.success:
            return {}

        formatted: dict[str, Any] = {}
        for ind in econ_result.data.get("indicators", []):
            key = f"{ind.get('indicator_id', 'unknown')}_{ind.get('country', 'WLD')}"
            values = ind.get("values", [])
            if values:
                formatted[key] = {
                    "latest_value": values[0].get("value"),
                    "latest_date": values[0].get("date"),
                    "country": ind.get("country"),
                    "data_points": len(values),
                }
        return formatted

    # ── REFLECT phase ──

    async def _synthesize(
        self,
        prompt: str,
        raw_context: str,
        skill_context: str = "",
        geo_hint: str = "",
        tenant_id: str = "",
    ) -> dict[str, Any]:
        """Use Claude to synthesize research findings."""
        default_synthesis = {
            "overview": f"Market research for: {prompt}",
            "sizing": {},
            "competitors": [],
            "trends": [],
            "findings": [f"Research gathered for: {prompt}"],
            "recommendations": ["Review raw data for detailed insights."],
            "confidence": 0.3,
            "methodology": ["Automated web search", "Economic indicator lookup"],
        }

        if self._anthropic_client is None:
            logger.warning(
                "STUB MODE: No Anthropic client — MRA_ANTHROPIC_API_KEY is not set. "
                "All results will be low-confidence stubs."
            )
            default_synthesis["findings"] = [
                "STUB MODE: MRA_ANTHROPIC_API_KEY is not configured on this deployment. "
                "Set the environment variable and redeploy for real LLM-powered results."
            ]
            return default_synthesis

        if not raw_context.strip():
            logger.warning(
                "No raw context for synthesis — all data-gathering skills returned empty. "
                "Check MRA_TAVILY_API_KEY and MRA_GNEWS_API_KEY."
            )
            default_synthesis["findings"] = [
                "DATA COLLECTION FAILED: All research skills returned empty results. "
                "Likely causes: MRA_TAVILY_API_KEY not set (web search disabled), "
                "MRA_GNEWS_API_KEY not set (news disabled), or external APIs unreachable."
            ]
            return default_synthesis

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_SYNTHESIS

                system = await self._prompt_loader.load(
                    "zorven-wf1-mra-synthesis",
                    tenant_id=tenant_id or None,
                    fallback=FALLBACK_SYNTHESIS,
                )
            else:
                system = _SYNTHESIS_SYSTEM_PROMPT
            if skill_context:
                system += f"\n\nAdditional methodology context:\n{skill_context[:2000]}"

            user_message = f"Research query: {prompt}\n\n"
            if geo_hint:
                user_message += f"{geo_hint}\n\n"
            user_message += f"Raw research data:\n{raw_context[:30000]}"

            message = await self._anthropic_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            tokens_used = getattr(message, "usage", None)
            if tokens_used:
                self._session_tokens += getattr(
                    tokens_used, "input_tokens", 0
                ) + getattr(tokens_used, "output_tokens", 0)

            content = next(
                b.text for b in message.content if b.type == "text"
            ).strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            synthesis = json.loads(content, strict=False)
            return synthesis
        except Exception as exc:
            logger.error(
                "Failed to synthesize via Claude: %s — %s",
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return default_synthesis
