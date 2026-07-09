"""PAOR engine for the Audience Persona Agent.

Implements Plan-Act-Observe-Reflect loop:
  1. PLAN: Claude decomposes query into skill sequence
  2. ACT (Phase 1): Research skills in parallel (SKL-APA-01..06, 05b, 05c)
  3. ACT (Phase 2): Analysis skills sequentially (SKL-APA-07..10)
  4. OBSERVE: Compile results, deduplicate sources
  5. REFLECT: Claude synthesizes personas + journey maps

PAOR states: IDLE → INPUT_GUARDRAILS → PLANNING → RESEARCHING →
  PROFILING → SYNTHESIZING → MAPPING → OUTPUT_GUARDRAILS →
  PERSISTING → COMPLETED
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from app.circuit_breaker.breaker import CircuitBreaker, CircuitOpenError
from app.core.config import settings
from app.events.catalog import EventEmitter, EventType
from app.logic.guardrails import ThreeLayerGuardrails
from app.skills.models import SkillContext, SkillResult
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Research skills (Phase 1 — parallel)
_RESEARCH_SKILLS = [
    "SKL-APA-01",
    "SKL-APA-02",
    "SKL-APA-03",
    "SKL-APA-04",
    "SKL-APA-05",
    "SKL-APA-06",
]

# Odoo research skills (Phase 1 — parallel, only when enabled)
_ODOO_SKILLS = ["SKL-APA-05b", "SKL-APA-05c"]

# Analysis skills (Phase 2 — sequential)
_ANALYSIS_SKILLS = [
    "SKL-APA-07",
    "SKL-APA-08",
    "SKL-APA-09",
    "SKL-APA-10",
]

# Default plan (no LLM available)
_DEFAULT_PLAN = [
    "SKL-APA-01",
    "SKL-APA-04",
    "SKL-APA-07",
    "SKL-APA-09",
]


class PersonaAnalyzer:
    """PAOR engine for audience persona generation."""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        guardrails: ThreeLayerGuardrails,
        circuit_breakers: dict[str, CircuitBreaker],
        event_emitter: EventEmitter,
        anthropic_client: Any = None,
        prompt_loader: Any = None,
    ) -> None:
        self._registry = skill_registry
        self._guardrails = guardrails
        self._breakers = circuit_breakers
        self._events = event_emitter
        self._anthropic = anthropic_client
        self._prompt_loader = prompt_loader

    async def analyze(
        self,
        prompt: str,
        *,
        tenant_id: str = "",
        user_role: str = "EDITOR",
        config: dict[str, Any] | None = None,
        previous_outputs: dict[str, Any] | None = None,
        skill_context: str = "",
    ) -> dict[str, Any]:
        """Execute the full PAOR analysis loop."""
        session_id = str(uuid.uuid4())
        config = config or {}
        previous_outputs = previous_outputs or {}
        start_time = time.monotonic()
        tokens_used = 0

        await self._events.emit(
            EventType.SESSION_STARTED,
            session_id=session_id,
            tenant_id=tenant_id,
            detail={"prompt_length": len(prompt)},
        )

        # ── PLAN ──
        skill_sequence = await self._create_plan(
            prompt, config, previous_outputs, session_id, tenant_id
        )

        await self._events.emit(
            EventType.PLAN_CREATED,
            session_id=session_id,
            tenant_id=tenant_id,
            detail={"skill_sequence": skill_sequence},
        )

        # Check plan guardrails
        plan_check = self._guardrails.plan_tool_guardrails.check_plan(skill_sequence)
        if not plan_check.passed:
            return self._error_response(prompt, plan_check.message, plan_check.rule)

        # ── ACT: Phase 1 — Research (parallel) ──
        research_skills = [
            sid for sid in skill_sequence if sid in set(_RESEARCH_SKILLS + _ODOO_SKILLS)
        ]
        analysis_skills = [
            sid for sid in skill_sequence if sid in set(_ANALYSIS_SKILLS)
        ]

        skill_results: dict[str, SkillResult] = {}
        context = SkillContext(
            session_id=session_id,
            tenant_id=tenant_id,
            user_role=user_role,
            skill_context_text=skill_context,
            config=config,
        )

        if research_skills:
            phase1_results = await self._execute_parallel(
                research_skills, prompt, context, previous_outputs, tokens_used
            )
            skill_results.update(phase1_results)
            tokens_used += sum(r.tokens_used for r in phase1_results.values())

        # ── ACT: Phase 2 — Analysis (sequential) ──
        for skill_id in analysis_skills:
            # Update context with previous results
            context.previous_skill_results = {
                sid: r.data for sid, r in skill_results.items() if r.success
            }

            tool_check = self._guardrails.plan_tool_guardrails.check_tool(
                skill_id, user_role, tokens_used
            )
            if not tool_check.passed:
                logger.warning("Guardrail blocked %s: %s", skill_id, tool_check.message)
                continue

            result = await self._execute_skill(
                skill_id,
                self._build_skill_input(
                    skill_id, prompt, skill_results, previous_outputs
                ),
                context,
            )
            if result:
                skill_results[skill_id] = result
                tokens_used += result.tokens_used

        # ── OBSERVE ──
        raw_context, sources = self._compile_skill_results(skill_results)

        # ── REFLECT — Synthesize ──
        synthesis = await self._synthesize(
            prompt,
            raw_context,
            previous_outputs,
            skill_context,
            skill_results,
            session_id,
            tenant_id,
        )
        tokens_used += synthesis.get("_tokens_used", 0)

        # Normalize per-persona scores (LLMs may return 85 instead of 0.85)
        for persona in synthesis.get("personas", []):
            if isinstance(persona, dict):
                if "confidence_score" in persona:
                    persona["confidence_score"] = _normalize_confidence(
                        persona["confidence_score"]
                    )
                if "priority_score" in persona:
                    persona["priority_score"] = _normalize_confidence(
                        persona["priority_score"]
                    )

        # Build response
        response = {
            "query": prompt,
            "personas": synthesis.get("personas", []),
            "journey_maps": synthesis.get("journey_maps", []),
            "segment_matrix": synthesis.get("segment_matrix", {}),
            "executive_summary": _to_markdown_str(
                synthesis.get("executive_summary", "")
            ),
            "sources": [s for s in sources],
            "findings": _flatten_list_to_strings(synthesis.get("findings", [])),
            "recommendations": _flatten_list_to_strings(
                synthesis.get("recommendations", [])
            ),
            "raw_context": raw_context[: settings.OUTPUT_MAX_CHARS],
            "confidence_score": _normalize_confidence(
                synthesis.get("confidence_score", 0.0)
            ),
            "methodology_notes": synthesis.get("methodology_notes", ""),
        }

        # ── L3 Output Guardrails ──
        response = self._guardrails.output_guardrails.check(response)

        await self._events.emit(
            EventType.OUTPUT_GUARDRAIL_APPLIED,
            session_id=session_id,
            tenant_id=tenant_id,
        )

        duration_ms = (time.monotonic() - start_time) * 1000
        await self._events.emit(
            EventType.SESSION_COMPLETED,
            session_id=session_id,
            tenant_id=tenant_id,
            detail={
                "duration_ms": round(duration_ms),
                "tokens_used": tokens_used,
                "personas_count": len(response.get("personas", [])),
                "sources_count": len(response.get("sources", [])),
            },
        )

        return response

    # ── Planning ──

    async def _create_plan(
        self,
        prompt: str,
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
        session_id: str,
        tenant_id: str,
    ) -> list[str]:
        """Use Claude to create a skill execution plan."""
        if not self._anthropic:
            logger.info("No Anthropic client, using default plan")
            return list(_DEFAULT_PLAN)

        try:
            has_mra = "market_research" in previous_outputs
            has_cia = "competitor_intelligence" in previous_outputs
            odoo_enabled = settings.ODOO_ENABLED

            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_PLANNING

                odoo_skills_text = (
                    "- SKL-APA-05b: Odoo survey data extraction\n"
                    "- SKL-APA-05c: Odoo CRM customer extraction\n"
                    if odoo_enabled
                    else ""
                )
                upstream_hints = ""
                if has_mra:
                    upstream_hints += (
                        "- MRA data available: skip SKL-APA-01 unless deeper "
                        "audience-specific research needed\n"
                    )
                if has_cia:
                    upstream_hints += (
                        "- CIA data available: use for competitor audience "
                        "comparison in SKL-APA-08/09\n"
                    )
                system_prompt = await self._prompt_loader.load(
                    "zorven-wf1-apa-planning",
                    tenant_id=tenant_id or None,
                    variables={
                        "odoo_skills": odoo_skills_text,
                        "upstream_hints": upstream_hints,
                        "context.odoo_skills": odoo_skills_text,
                        "context.upstream_hints": upstream_hints,
                    },
                    fallback=FALLBACK_PLANNING,
                )
            else:
                system_prompt = (
                    "You are a persona research planner. Given a user query, "
                    "select which research and analysis skills to execute.\n\n"
                    "Available research skills:\n"
                    "- SKL-APA-01: Audience landscape research (Tavily web search)\n"
                    "- SKL-APA-02: Forum/community mining\n"
                    "- SKL-APA-03: Social listening analysis\n"
                    "- SKL-APA-04: Buyer role extraction\n"
                    "- SKL-APA-05: Review/needs mining\n"
                    "- SKL-APA-06: RAG context retrieval\n"
                )
                if odoo_enabled:
                    system_prompt += (
                        "- SKL-APA-05b: Odoo survey data extraction\n"
                        "- SKL-APA-05c: Odoo CRM customer extraction\n"
                    )
                system_prompt += (
                    "\nAnalysis skills (always sequential):\n"
                    "- SKL-APA-07: Demographic profile builder\n"
                    "- SKL-APA-08: Psychographic/behavioral profiler\n"
                    "- SKL-APA-09: Persona synthesizer/differentiator\n"
                    "- SKL-APA-10: Buying journey mapper\n\n"
                    "Rules:\n"
                    "- Research skills run in parallel, analysis sequentially\n"
                    "- Always include SKL-APA-07 and SKL-APA-09 at minimum\n"
                    "- Include SKL-APA-10 if journey mapping is requested\n"
                )
                if has_mra:
                    system_prompt += (
                        "- MRA data available: skip SKL-APA-01 unless deeper "
                        "audience-specific research needed\n"
                    )
                if has_cia:
                    system_prompt += (
                        "- CIA data available: use for competitor audience "
                        "comparison in SKL-APA-08/09\n"
                    )

                system_prompt += (
                    "\nReturn a JSON array of skill IDs in execution order. "
                    "Research skills first, then analysis skills."
                )

            breaker = self._breakers.get("llm")
            if breaker:
                response = await breaker.call(
                    self._call_anthropic,
                    system_prompt,
                    f"Plan persona research for: {prompt}",
                )
            else:
                response = await self._call_anthropic(
                    system_prompt,
                    f"Plan persona research for: {prompt}",
                )

            text = next(b.text for b in response.content if b.type == "text")
            # Extract JSON array
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            skill_ids = json.loads(text, strict=False)
            if isinstance(skill_ids, list):
                # Filter to valid IDs
                valid = [
                    sid
                    for sid in skill_ids
                    if sid
                    in {
                        "SKL-APA-01",
                        "SKL-APA-02",
                        "SKL-APA-03",
                        "SKL-APA-04",
                        "SKL-APA-05",
                        "SKL-APA-05b",
                        "SKL-APA-05c",
                        "SKL-APA-06",
                        "SKL-APA-07",
                        "SKL-APA-08",
                        "SKL-APA-09",
                        "SKL-APA-10",
                    }
                ]
                if valid:
                    return valid

        except CircuitOpenError:
            logger.warning("LLM circuit open, using default plan")
        except Exception:
            logger.warning("Plan creation failed, using default plan", exc_info=True)

        return list(_DEFAULT_PLAN)

    # ── Execution ──

    async def _execute_parallel(
        self,
        skill_ids: list[str],
        prompt: str,
        context: SkillContext,
        previous_outputs: dict[str, Any],
        tokens_used: int,
    ) -> dict[str, SkillResult]:
        """Execute research skills in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_WEB_REQUESTS)
        results: dict[str, SkillResult] = {}

        async def _run(sid: str) -> tuple[str, SkillResult | None]:
            async with semaphore:
                tool_check = self._guardrails.plan_tool_guardrails.check_tool(
                    sid, context.user_role, tokens_used
                )
                if not tool_check.passed:
                    logger.warning("Guardrail blocked %s: %s", sid, tool_check.message)
                    return sid, None
                input_data = self._build_skill_input(sid, prompt, {}, previous_outputs)
                result = await self._execute_skill(sid, input_data, context)
                return sid, result

        tasks = [_run(sid) for sid in skill_ids]
        for coro in asyncio.as_completed(tasks):
            sid, result = await coro
            if result:
                results[sid] = result

        return results

    async def _execute_skill(
        self,
        skill_id: str,
        input_data: dict[str, Any],
        context: SkillContext,
    ) -> SkillResult | None:
        """Execute a single skill with circuit breaker protection."""
        skill = self._registry.get_skill(skill_id)
        if not skill:
            logger.warning("Skill %s not registered", skill_id)
            return None

        await self._events.emit(
            EventType.TOOL_CALLED,
            session_id=context.session_id,
            tenant_id=context.tenant_id,
            detail={"skill_id": skill_id},
        )

        cb_name = skill.meta.circuit_breaker_dependency
        breaker = self._breakers.get(cb_name) if cb_name else None

        try:
            if breaker:
                result = await breaker.call(skill.execute, input_data, context)
            else:
                result = await skill.execute(input_data, context)

            await self._events.emit(
                EventType.TOOL_COMPLETED,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                detail={
                    "skill_id": skill_id,
                    "success": result.success,
                    "duration_ms": result.duration_ms,
                },
            )
            return result

        except CircuitOpenError as exc:
            logger.warning("Circuit open for %s: %s", skill_id, exc)
            await self._events.emit(
                EventType.CIRCUIT_BREAKER_OPENED,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                detail={"skill_id": skill_id, "circuit": exc.circuit_name},
            )
            return None

        except Exception as exc:
            logger.error("Skill %s failed: %s", skill_id, exc, exc_info=True)
            await self._events.emit(
                EventType.TOOL_FAILED,
                session_id=context.session_id,
                tenant_id=context.tenant_id,
                detail={"skill_id": skill_id, "error": str(exc)},
            )
            return None

    # ── Input Building ──

    @staticmethod
    def _build_skill_input(
        skill_id: str,
        prompt: str,
        skill_results: dict[str, SkillResult],
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Build skill-specific input data."""
        base: dict[str, Any] = {"prompt": prompt}

        # Inject MRA context for enrichment skills
        mra_data = previous_outputs.get("market_research", {})
        if mra_data:
            base["mra_context"] = mra_data

        # Inject CIA context
        cia_data = previous_outputs.get("competitor_intelligence", {})
        if cia_data:
            base["cia_context"] = cia_data

        # Add previous skill results for sequential skills
        if skill_id in {"SKL-APA-07", "SKL-APA-08", "SKL-APA-09", "SKL-APA-10"}:
            base["research_results"] = {
                sid: r.data for sid, r in skill_results.items() if r.success
            }

        return base

    # ── Observation ──

    @staticmethod
    def _compile_skill_results(
        skill_results: dict[str, SkillResult],
    ) -> tuple[str, list[dict[str, str]]]:
        """Compile all skill results into raw context and deduplicated sources."""
        context_parts: list[str] = []
        seen_urls: set[str] = set()
        sources: list[dict[str, str]] = []

        for skill_id, result in sorted(skill_results.items()):
            if not result.success:
                continue
            data = result.data

            # Compile context
            context_str = data.get("context", "")
            if context_str:
                context_parts.append(f"## {skill_id}\n{context_str}")

            # Deduplicate sources
            for source in data.get("sources", []):
                if isinstance(source, dict):
                    url = source.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        sources.append(source)

        raw_context = "\n\n".join(context_parts)
        return raw_context, sources

    # ── Reflection / Synthesis ──

    async def _synthesize(
        self,
        prompt: str,
        raw_context: str,
        previous_outputs: dict[str, Any],
        skill_context: str,
        skill_results: dict[str, SkillResult],
        session_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Use Claude to synthesize personas and journey maps."""
        if not self._anthropic:
            stub = self._stub_synthesis(prompt, skill_results)
            stub["findings"] = [
                "STUB MODE: APA_ANTHROPIC_API_KEY is not configured "
                "on this deployment."
            ]
            return stub

        try:
            mra_context = ""
            mra_data = previous_outputs.get("market_research", {})
            if mra_data:
                mra_context = (
                    f"\n\nMarket Research Context:\n"
                    f"Market: {mra_data.get('market_overview', '')}\n"
                    f"Sizing: {json.dumps(mra_data.get('market_sizing', {}))}\n"
                )

            cia_context = ""
            cia_data = previous_outputs.get("competitor_intelligence", {})
            if cia_data:
                competitors = cia_data.get("competitors", [])
                cia_context = (
                    f"\n\nCompetitor Intelligence:\n"
                    f"Competitors: {json.dumps(competitors[:5])}\n"
                )

            max_personas = min(settings.MAX_PERSONAS, settings.MAX_PERSONAS_LIMIT)

            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_SYNTHESIS

                system_prompt = await self._prompt_loader.load(
                    "zorven-wf1-apa-synthesis",
                    tenant_id=tenant_id or None,
                    fallback=FALLBACK_SYNTHESIS,
                )
                # Inject max_personas into the loaded prompt
                system_prompt = system_prompt.replace(
                    "up to 5 distinct personas",
                    f"up to {max_personas} distinct personas",
                )
            else:
                system_prompt = (
                    "You are an expert audience research analyst. Synthesize "
                    "the research data into structured buyer personas.\n\n"
                    "Requirements:\n"
                    f"- Generate up to {max_personas} distinct personas\n"
                    "- Each persona must have: slug, segment_label, demographics, "
                    "psychographics, pain_points, motivations, objections, "
                    "preferred_channels, priority_score, narrative, confidence_score\n"
                    "- NEVER use fictional human names for personas. Use "
                    "descriptive segment labels (e.g., 'Enterprise Decision Maker', "
                    "'Growth-Stage Startup Founder')\n"
                    "- Include buying journey maps with stages: Awareness, "
                    "Consideration, Evaluation, Decision, Onboarding, Advocacy\n"
                    "- Cite sources for all claims\n"
                    "- Flag low-confidence claims\n\n"
                    "Return valid JSON with keys: personas, journey_maps, "
                    "segment_matrix, executive_summary, findings, recommendations, "
                    "confidence_score, methodology_notes"
                )

            if skill_context:
                system_prompt += f"\n\nMethodology guidance:\n{skill_context}"

            user_message = (
                f"Query: {prompt}\n\n"
                f"Research Data:\n{raw_context[:50000]}"
                f"{mra_context}{cia_context}"
            )

            breaker = self._breakers.get("llm")
            if breaker:
                response = await breaker.call(
                    self._call_anthropic,
                    system_prompt,
                    user_message,
                )
            else:
                response = await self._call_anthropic(
                    system_prompt,
                    user_message,
                )

            text = next(b.text for b in response.content if b.type == "text")
            tokens = getattr(response.usage, "output_tokens", 0) + getattr(
                response.usage, "input_tokens", 0
            )

            # Parse JSON
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            try:
                result = json.loads(text, strict=False)
            except json.JSONDecodeError:
                result = _repair_truncated_json(text)
            result["_tokens_used"] = tokens
            return result

        except CircuitOpenError:
            logger.warning("LLM circuit open during synthesis")
            stub = self._stub_synthesis(prompt, skill_results)
            stub["findings"] = [
                "STUB MODE: LLM circuit breaker is open — "
                "APA_ANTHROPIC_API_KEY may be misconfigured."
            ]
            return stub
        except Exception:
            logger.error("Synthesis failed", exc_info=True)
            stub = self._stub_synthesis(prompt, skill_results)
            stub["findings"] = [
                "STUB MODE: LLM synthesis failed unexpectedly. "
                "Check APA_ANTHROPIC_API_KEY configuration."
            ]
            return stub

    @staticmethod
    def _stub_synthesis(
        prompt: str,
        skill_results: dict[str, SkillResult],
    ) -> dict[str, Any]:
        """Return stub synthesis when LLM is unavailable."""
        findings = []
        for sid, result in skill_results.items():
            if result.success and result.data.get("context"):
                findings.append(
                    f"Research from {sid}: " f"{result.data['context'][:200]}"
                )

        return {
            "personas": [
                {
                    "slug": "primary-audience",
                    "segment_label": "Primary Target Audience",
                    "demographics": {},
                    "psychographics": {},
                    "pain_points": ["Needs further research"],
                    "motivations": ["Needs further research"],
                    "objections": [],
                    "preferred_channels": [],
                    "priority_score": 0.5,
                    "narrative": (
                        "Stub persona generated without LLM analysis. "
                        "Research data was collected but requires AI "
                        "synthesis for actionable insights."
                    ),
                    "data_source": "research_based",
                    "confidence_score": 0.3,
                    "citations": [],
                }
            ],
            "journey_maps": [],
            "segment_matrix": {},
            "executive_summary": (
                f"Audience research completed for: {prompt}. "
                "LLM synthesis unavailable — stub results provided."
            ),
            "findings": findings or ["Research data collected (stub mode)"],
            "recommendations": [
                "Re-run analysis with LLM enabled for full persona synthesis"
            ],
            "confidence_score": 0.3,
            "methodology_notes": "Stub mode — no LLM synthesis available",
            "_tokens_used": 0,
        }

    # ── LLM Helper ──

    async def _call_anthropic(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Any:
        """Call the Anthropic API."""
        return await self._anthropic.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            thinking={"type": "disabled"},
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

    # ── Error Response ──

    @staticmethod
    def _error_response(prompt: str, message: str, rule: str) -> dict[str, Any]:
        """Build an error response."""
        return {
            "query": prompt,
            "personas": [],
            "journey_maps": [],
            "segment_matrix": {},
            "executive_summary": "",
            "sources": [],
            "findings": [f"Guardrail {rule}: {message}"],
            "recommendations": [],
            "raw_context": "",
            "confidence_score": 0.0,
            "methodology_notes": f"Blocked by guardrail {rule}",
        }


def _to_markdown_str(value: Any) -> str:
    """Convert a value to a markdown string.

    If the LLM returns a dict for executive_summary, convert its
    key-value pairs into readable markdown paragraphs.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            label = k.replace("_", " ").title()
            parts.append(f"**{label}:** {v}")
        return "\n\n".join(parts)
    if value is None:
        return ""
    return str(value)


def _flatten_list_to_strings(items: list) -> list[str]:
    """Ensure every item in a list is a string.

    If the LLM returns dicts in findings/recommendations, extract the
    meaningful text from known keys.
    """
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Try common LLM keys: recommendation, finding, text, summary
            text = (
                item.get("recommendation")
                or item.get("finding")
                or item.get("text")
                or item.get("summary")
                or item.get("rationale")
            )
            if text and isinstance(text, str):
                priority = item.get("priority", "")
                if priority:
                    result.append(f"[{priority}] {text}")
                else:
                    result.append(text)
            else:
                # Fallback: join all string values
                vals = [str(v) for v in item.values() if v]
                if vals:
                    result.append(" — ".join(vals))
    return result


def _normalize_confidence(value: Any) -> float:
    """Normalize a score to 0.0-1.0 range.

    Handles three common LLM return formats:
      - 0.0-1.0: already normalized, return as-is
      - 1-10: divide by 10 (e.g., 8.5 → 0.85)
      - 11-100: divide by 100 (e.g., 75 → 0.75)
    """
    if not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return 0.0
    if value > 10.0:
        return value / 100.0
    if value > 1.0:
        return value / 10.0
    return float(value)


def _repair_truncated_json(text: str) -> dict:
    """Attempt to repair truncated JSON from LLM output."""
    for cutoff in ('"}\n', '"},', '"}]', '"}'):
        idx = text.rfind(cutoff)
        if idx > 0:
            candidate = text[: idx + len(cutoff)]
            open_braces = candidate.count("{") - candidate.count("}")
            open_brackets = candidate.count("[") - candidate.count("]")
            candidate += "]" * max(open_brackets, 0)
            candidate += "}" * max(open_braces, 0)
            try:
                result = json.loads(candidate, strict=False)
                if isinstance(result, dict):
                    logger.warning(
                        "Repaired truncated JSON (%d chars trimmed)",
                        len(text) - len(candidate),
                    )
                    return result
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("Could not repair truncated JSON", text, 0)
