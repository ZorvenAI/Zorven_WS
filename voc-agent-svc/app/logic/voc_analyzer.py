"""VoCA PAOR Analyzer — Plan → Act → Observe → Reflect engine.

State machine:
IDLE → DETECTING_MODE → PLANNING → [INGESTING] → MINING → ANALYZING
  → SYNTHESIZING → OUTPUT_CHECK → PERSISTING → COMPLETED
"""

import asyncio
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.events.catalog import EventEmitter, EventType
from app.logic.guardrails import ThreeLayerGuardrails
from app.skills.models import SkillContext, SkillResult
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# LLM synthesis system prompt
_SYNTHESIS_SYSTEM_PROMPT = """You are a Voice of Customer analysis expert. Synthesize the
collected customer feedback data into a comprehensive VoC intelligence report.

Your analysis must include:
1. **Executive Summary**: 2-3 paragraph overview of customer sentiment landscape
2. **Sentiment Analysis**: Overall and per-channel sentiment with emotion profiles
3. **Theme Clusters**: Hierarchical themes with severity scores and representative quotes
4. **NPS Analysis**: If available, NPS trends and driver decomposition
5. **Pain Point Priority Matrix**: Ranked by severity × frequency × persona impact
6. **VoC Health Score**: 0-100 weighted composite
7. **Strategy Bridge**: Actionable recommendations linking VoC to business strategy

Output valid JSON matching this structure:
{
    "executive_summary": "...",
    "sentiment": {
        "overall_sentiment": {"positive": 0.0, "neutral": 0.0, "negative": 0.0},
        "emotion_profile": {"joy": 0, "trust": 0, "anger": 0, "sadness": 0, ...},
        "channel_sentiments": [{"channel": "...", "sentiment": {...}, "feedback_count": 0}],
        "data_coverage_score": 0.0
    },
    "themes": {
        "themes": [{"theme_slug": "...", "theme_name": "...", "feedback_count": 0,
                     "severity_score": 0.0, "sub_themes": [...]}],
        "total_feedback_analyzed": 0
    },
    "nps_analysis": {"nps_available": false, "current_nps": {}, "drivers": []},
    "pain_point_priority_matrix": {"pain_points": [{"name": "...", "severity": 0.0, ...}]},
    "voc_health_score": 0.0,
    "findings": ["..."],
    "recommendations": ["..."],
    "confidence_score": 0.0
}"""


class VoCAAnalyzer:
    """PAOR engine for Voice of Customer analysis."""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        guardrails: ThreeLayerGuardrails,
        circuit_breakers: dict[str, Any],
        event_emitter: EventEmitter,
        anthropic_client: Any = None,
    ) -> None:
        self._skills = skill_registry
        self._guardrails = guardrails
        self._breakers = circuit_breakers
        self._events = event_emitter
        self._anthropic = anthropic_client

    async def analyze(
        self,
        prompt: str,
        tenant_id: str = "default",
        user_role: str = "EDITOR",
        config: dict[str, Any] | None = None,
        previous_outputs: dict[str, Any] | None = None,
        skill_context: str = "",
    ) -> dict[str, Any]:
        """Run the full PAOR analysis pipeline."""
        config = config or {}
        previous_outputs = previous_outputs or {}
        session_id = f"voca-{tenant_id}-{int(time.time())}"
        total_tokens = 0
        all_sources: list[dict[str, str]] = []
        raw_context_parts: list[str] = []
        start_time = time.time()

        # Extract upstream context
        mra_data = previous_outputs.get("market_research", {})
        cia_data = previous_outputs.get("competitor_intelligence", {})
        apa_data = previous_outputs.get("audience_persona", {})
        tcia_data = previous_outputs.get("trend_cultural", {})

        company_name = self._extract_company_name(prompt, previous_outputs)

        # ── DETECTING MODE ──
        operating_mode = await self._detect_operating_mode(tenant_id)
        await self._events.emit(
            EventType.MODE_DETECTED,
            tenant_id=tenant_id,
            session_id=session_id,
            data={"operating_mode": operating_mode},
        )
        if operating_mode == "external_only":
            await self._events.emit(
                EventType.MODE_EXTERNAL_ONLY,
                tenant_id=tenant_id,
                session_id=session_id,
            )

        # ── INPUT GUARDRAILS ──
        input_results = await self._guardrails.check_input(
            prompt,
            {"tenant_id": tenant_id, "user_role": user_role},
            previous_outputs,
        )
        blocked = [r for r in input_results if not r.passed]
        if blocked:
            await self._events.emit(
                EventType.GUARDRAIL_INPUT_BLOCKED,
                tenant_id=tenant_id,
                session_id=session_id,
                data={"rules": [r.rule for r in blocked]},
            )
            return self._error_response(
                prompt,
                f"Input blocked: {blocked[0].rule} — {blocked[0].message}",
            )
        await self._events.emit(
            EventType.GUARDRAIL_INPUT_PASSED,
            tenant_id=tenant_id,
            session_id=session_id,
        )

        # ── PLANNING ──
        skill_sequence = self._plan_skills(operating_mode, user_role, config)
        await self._events.emit(
            EventType.PLAN_CREATED,
            tenant_id=tenant_id,
            session_id=session_id,
            data={"skills": skill_sequence, "mode": operating_mode},
        )

        # Build skill context
        ctx = SkillContext(
            session_id=session_id,
            tenant_id=tenant_id,
            user_role=user_role,
            previous_outputs=previous_outputs,
            skill_context_text=skill_context,
            config=config,
            operating_mode=operating_mode,
        )
        skill_results: dict[str, SkillResult] = {}

        # ── INGESTING (Full Mode only) ──
        if operating_mode == "full":
            odoo_skills = [
                s for s in skill_sequence
                if s in ("SKL-VoCA-01", "SKL-VoCA-02", "SKL-VoCA-03")
            ]
            odoo_results = await self._execute_skills_parallel(
                odoo_skills,
                {"company_name": company_name, "prompt": prompt},
                ctx,
            )
            skill_results.update(odoo_results)
            for sr in odoo_results.values():
                total_tokens += sr.tokens_used
                all_sources.extend(sr.sources)
                if sr.data:
                    raw_context_parts.append(json.dumps(sr.data)[:3000])

            # Segment linking (SKL-VoCA-04)
            if "SKL-VoCA-04" in skill_sequence:
                ctx.previous_skill_results = {
                    k: v.data for k, v in skill_results.items()
                }
                sr04 = await self._execute_skill(
                    "SKL-VoCA-04",
                    {"company_name": company_name, "prompt": prompt},
                    ctx,
                )
                if sr04:
                    skill_results["SKL-VoCA-04"] = sr04

        # ── MINING (parallel external research) ──
        mining_skills = [
            s for s in skill_sequence
            if s in ("SKL-VoCA-05", "SKL-VoCA-06", "SKL-VoCA-07", "SKL-VoCA-08")
        ]
        mining_results = await self._execute_skills_parallel(
            mining_skills,
            {"company_name": company_name, "prompt": prompt},
            ctx,
        )
        skill_results.update(mining_results)
        for sr in mining_results.values():
            total_tokens += sr.tokens_used
            all_sources.extend(sr.sources)
            if sr.data:
                raw_context_parts.append(json.dumps(sr.data)[:3000])

        # Update context with all research results
        ctx.previous_skill_results = {
            k: v.data for k, v in skill_results.items()
        }

        # ── ANALYZING (sequential LLM skills) ──
        analysis_skills = [
            s for s in skill_sequence
            if s in ("SKL-VoCA-09", "SKL-VoCA-10", "SKL-VoCA-11", "SKL-VoCA-12")
        ]
        for skill_id in analysis_skills:
            # Check token budget
            budget_check = self._guardrails.plan_guardrails.check_token_budget(
                total_tokens
            )
            if not budget_check.passed:
                logger.warning("Token budget exceeded, stopping analysis")
                break

            sr = await self._execute_skill(
                skill_id,
                {"company_name": company_name, "prompt": prompt},
                ctx,
            )
            if sr:
                skill_results[skill_id] = sr
                total_tokens += sr.tokens_used
                all_sources.extend(sr.sources)
                if sr.data:
                    raw_context_parts.append(json.dumps(sr.data)[:3000])
                ctx.previous_skill_results[skill_id] = sr.data

        # ── OUTPUT GUARDRAILS ──
        # Compile preliminary result for checking
        preliminary = self._compile_result(
            prompt, operating_mode, skill_results, all_sources,
            "\n---\n".join(raw_context_parts),
        )

        output_results = await self._guardrails.check_output(
            preliminary, tenant_id
        )
        blocked_output = [r for r in output_results if not r.passed]
        if blocked_output:
            await self._events.emit(
                EventType.GUARDRAIL_OUTPUT_BLOCKED,
                tenant_id=tenant_id,
                session_id=session_id,
                data={"rules": [r.rule for r in blocked_output]},
            )
            # Continue but flag
            logger.warning(
                "Output guardrails flagged: %s",
                [r.rule for r in blocked_output],
            )
        else:
            await self._events.emit(
                EventType.GUARDRAIL_OUTPUT_PASSED,
                tenant_id=tenant_id,
                session_id=session_id,
            )

        # ── PERSISTING ──
        if "SKL-VoCA-13" in skill_sequence:
            ctx.previous_skill_results = {
                k: v.data for k, v in skill_results.items()
            }
            sr13 = await self._execute_skill(
                "SKL-VoCA-13",
                {
                    "company_name": company_name,
                    "prompt": prompt,
                    "result": preliminary,
                },
                ctx,
            )
            if sr13:
                skill_results["SKL-VoCA-13"] = sr13

        # Final compilation
        result = self._compile_result(
            prompt, operating_mode, skill_results, all_sources,
            "\n---\n".join(raw_context_parts),
        )

        elapsed = time.time() - start_time
        logger.info(
            "VoCA analysis complete: mode=%s, health=%.1f, tokens=%d, %.1fs",
            operating_mode,
            result.get("voc_health_score", 0),
            total_tokens,
            elapsed,
        )

        return result

    async def _detect_operating_mode(self, tenant_id: str) -> str:
        """Detect operating mode: full or external_only."""
        # Check if Odoo skills are registered
        odoo_skill = self._skills.get_skill("SKL-VoCA-01")
        if odoo_skill is not None:
            return "full"
        return "external_only"

    def _plan_skills(
        self,
        operating_mode: str,
        user_role: str,
        config: dict[str, Any],
    ) -> list[str]:
        """Create mode-aware skill execution plan."""
        plan: list[str] = []

        # Full Mode: include Odoo skills
        if operating_mode == "full":
            plan.extend([
                "SKL-VoCA-01",  # Helpdesk
                "SKL-VoCA-02",  # Survey
                "SKL-VoCA-03",  # Chatter
                "SKL-VoCA-04",  # Segment linker
            ])

        # External research (both modes)
        plan.extend([
            "SKL-VoCA-05",  # External reviews
            "SKL-VoCA-06",  # Social feedback
            "SKL-VoCA-07",  # Forum mining
            "SKL-VoCA-08",  # RAG retrieval
        ])

        # Analysis (both modes)
        plan.extend([
            "SKL-VoCA-09",  # Sentiment
            "SKL-VoCA-10",  # Themes
            "SKL-VoCA-11",  # NPS
            "SKL-VoCA-12",  # Strategy bridge
        ])

        # Persistence
        plan.append("SKL-VoCA-13")  # Report persister

        # Filter by registered skills and RBAC
        available = self._skills.skill_ids()
        plan = [s for s in plan if s in available]

        # RBAC filter
        plan = [
            s for s in plan
            if self._guardrails.plan_guardrails.check_skill_allowed(
                s, user_role
            ).passed
        ]

        return plan

    async def _execute_skills_parallel(
        self,
        skill_ids: list[str],
        input_data: dict[str, Any],
        context: SkillContext,
    ) -> dict[str, SkillResult]:
        """Execute multiple skills in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_RESEARCH)
        results: dict[str, SkillResult] = {}

        async def _run(sid: str) -> None:
            async with semaphore:
                sr = await self._execute_skill(sid, input_data, context)
                if sr:
                    results[sid] = sr

        tasks = [_run(sid) for sid in skill_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def _execute_skill(
        self,
        skill_id: str,
        input_data: dict[str, Any],
        context: SkillContext,
    ) -> SkillResult | None:
        """Execute a single skill with circuit breaker protection."""
        skill = self._skills.get_skill(skill_id)
        if not skill:
            logger.warning("Skill not found: %s", skill_id)
            return None

        await self._events.emit(
            EventType.TOOL_CALLED,
            tenant_id=context.tenant_id,
            session_id=context.session_id,
            data={"skill_id": skill_id},
        )

        cb_name = skill.meta.circuit_breaker_dependency
        breaker = self._breakers.get(cb_name) if cb_name else None

        try:
            if breaker:
                result = await breaker.call(
                    skill.execute, input_data, context
                )
            else:
                result = await skill.execute(input_data, context)

            await self._events.emit(
                EventType.TOOL_COMPLETED,
                tenant_id=context.tenant_id,
                session_id=context.session_id,
                data={
                    "skill_id": skill_id,
                    "success": result.success,
                    "duration_ms": result.duration_ms,
                },
            )
            return result

        except Exception as exc:
            logger.warning("Skill %s failed: %s", skill_id, exc)
            await self._events.emit(
                EventType.TOOL_FAILED,
                tenant_id=context.tenant_id,
                session_id=context.session_id,
                data={"skill_id": skill_id, "error": str(exc)[:200]},
            )
            return SkillResult(
                skill_id=skill_id,
                success=False,
                error=str(exc)[:500],
            )

    def _compile_result(
        self,
        query: str,
        operating_mode: str,
        skill_results: dict[str, SkillResult],
        all_sources: list[dict[str, str]],
        raw_context: str,
    ) -> dict[str, Any]:
        """Compile skill results into the VoCAResponse shape."""
        # Extract analysis results
        sentiment_data = self._get_skill_data(
            skill_results, "SKL-VoCA-09"
        )
        theme_data = self._get_skill_data(
            skill_results, "SKL-VoCA-10"
        )
        nps_data = self._get_skill_data(
            skill_results, "SKL-VoCA-11"
        )
        strategy_data = self._get_skill_data(
            skill_results, "SKL-VoCA-12"
        )

        # Calculate data coverage
        active_channels = []
        for sid, sr in skill_results.items():
            if sr.success and sr.data:
                if sid == "SKL-VoCA-01":
                    active_channels.append("odoo_helpdesk")
                elif sid == "SKL-VoCA-02":
                    active_channels.append("odoo_survey")
                elif sid == "SKL-VoCA-03":
                    active_channels.append("odoo_chatter")
                elif sid == "SKL-VoCA-05":
                    active_channels.append("reviews")
                elif sid == "SKL-VoCA-06":
                    active_channels.append("social_media")
                elif sid == "SKL-VoCA-07":
                    active_channels.append("forums")

        total_channels = 6  # helpdesk, survey, chatter, reviews, social, forums
        data_coverage = (
            len(active_channels) / total_channels * 100
            if total_channels > 0
            else 0
        )

        # Collect findings and recommendations
        findings = []
        recommendations = []
        for sr in skill_results.values():
            if sr.success and sr.data:
                findings.extend(sr.data.get("findings", []))
                recommendations.extend(sr.data.get("recommendations", []))

        # Use strategy bridge data if available
        voc_health = strategy_data.get("voc_health_score", 0.0)
        pain_points = strategy_data.get(
            "pain_point_priority_matrix", {}
        )
        confidence = strategy_data.get("confidence_score", 0.5)

        # Compile sources (deduplicate by URL)
        seen_urls: set[str] = set()
        unique_sources = []
        for s in all_sources:
            url = s.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_sources.append(s)

        return {
            "query": query,
            "operating_mode": operating_mode,
            "data_coverage_score": round(data_coverage, 1),
            "sentiment": sentiment_data,
            "themes": theme_data,
            "nps_analysis": nps_data,
            "pain_point_priority_matrix": pain_points,
            "strategy_bridge": strategy_data,
            "voc_health_score": round(voc_health, 1),
            "findings": findings[:20],
            "recommendations": recommendations[:10],
            "sources": unique_sources[:50],
            "confidence_score": round(confidence, 2),
            "raw_context": raw_context[:settings.OUTPUT_MAX_CHARS],
        }

    @staticmethod
    def _get_skill_data(
        results: dict[str, SkillResult], skill_id: str
    ) -> dict[str, Any]:
        sr = results.get(skill_id)
        if sr and sr.success:
            return sr.data
        return {}

    @staticmethod
    def _extract_company_name(
        prompt: str, previous_outputs: dict[str, Any]
    ) -> str:
        """Extract company name from prompt or upstream data."""
        # Check MRA output
        mra = previous_outputs.get("market_research", {})
        if isinstance(mra, dict):
            name = mra.get("company_name", "")
            if name:
                return name

        # Check for common patterns in prompt
        for prefix in ("for ", "about ", "analyze "):
            if prefix in prompt.lower():
                idx = prompt.lower().index(prefix) + len(prefix)
                words = prompt[idx:].split()[:3]
                return " ".join(words)

        return ""

    @staticmethod
    def _error_response(query: str, error: str) -> dict[str, Any]:
        return {
            "query": query,
            "operating_mode": "",
            "data_coverage_score": 0.0,
            "sentiment": {},
            "themes": {},
            "nps_analysis": {},
            "pain_point_priority_matrix": {},
            "strategy_bridge": {},
            "voc_health_score": 0.0,
            "findings": [error],
            "recommendations": [],
            "sources": [],
            "confidence_score": 0.0,
            "raw_context": "",
        }
