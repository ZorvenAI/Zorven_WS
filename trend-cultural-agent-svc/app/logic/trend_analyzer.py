"""Core trend analysis engine — orchestrates all skills.

Pipeline: research (parallel) -> scoring -> mapping -> alerting -> synthesis.
"""

import asyncio
import logging
from typing import Any

from app.skills.models import SkillContext, SkillResult

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """Central orchestration engine for trend/cultural analysis."""

    def __init__(
        self,
        skill_registry: Any,
        guardrails: Any,
        trend_registry: Any,
        redis_manager: Any,
        alert_producer: Any,
        event_emitter: Any,
        settings: Any,
    ) -> None:
        self._skills = skill_registry
        self._guardrails = guardrails
        self._trend_registry = trend_registry
        self._redis = redis_manager
        self._alert_producer = alert_producer
        self._events = event_emitter
        self._settings = settings

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
        """Full analysis pipeline."""
        config = config or {}
        previous_outputs = previous_outputs or {}

        ctx = SkillContext(
            tenant_id=tenant_id,
            user_role=user_role,
            config=config,
        )

        # ── Step 1: Extract upstream context ──
        market_context = previous_outputs.get("market_research", {})
        competitor_context = previous_outputs.get("competitor_intelligence", {})
        persona_context = previous_outputs.get("audience_persona", {})

        industry = self._extract_industry(market_context, prompt)
        personas = persona_context.get("personas", [])
        competitors = competitor_context.get("competitors", [])

        # ── Step 2: Input guardrails ──
        input_result = await self._guardrails.validate_input(
            prompt, tenant_id, user_role, previous_outputs
        )
        if input_result.blocked:
            return {
                "error": input_result.block_reason,
                "findings": [input_result.block_reason],
                "sources": [],
                "scored_trends": [],
                "trend_report": {
                    "executive_summary": input_result.block_reason,
                    "trend_scorecard": [],
                    "confidence_score": 0.0,
                },
            }

        # ── Step 3: RAG context retrieval (SKL-TCIA-06) ──
        rag_result = await self._execute_skill(
            "SKL-TCIA-06",
            {"prompt": f"trend analysis {industry}", "top_k": 5},
            ctx,
        )
        rag_context = rag_result.data if rag_result.success else {}

        # ── Step 4: Research phase (parallel) ──
        semaphore = asyncio.Semaphore(self._settings.MAX_CONCURRENT_RESEARCH)
        research_tasks = [
            self._bounded_skill(
                semaphore,
                "SKL-TCIA-01",
                {
                    "industry": industry,
                    "persona_keywords": self._extract_persona_keywords(personas),
                    "platforms": [
                        "twitter",
                        "tiktok",
                        "reddit",
                        "linkedin",
                        "instagram",
                    ],
                    "lookback_hours": 72,
                },
                ctx,
            ),
            self._bounded_skill(
                semaphore,
                "SKL-TCIA-02",
                {
                    "industry": industry,
                    "cultural_domains": [
                        "values",
                        "lifestyle",
                        "work",
                        "sustainability",
                        "tech_adoption",
                    ],
                },
                ctx,
            ),
            self._bounded_skill(
                semaphore,
                "SKL-TCIA-03",
                {
                    "industry": industry,
                    "persona_platforms": self._extract_persona_platforms(personas),
                },
                ctx,
            ),
            self._bounded_skill(
                semaphore,
                "SKL-TCIA-04",
                {
                    "industry": industry,
                    "persona_age_ranges": self._extract_age_ranges(personas),
                    "generations": ["gen_z", "millennial", "gen_x", "boomer"],
                },
                ctx,
            ),
            self._bounded_skill(
                semaphore,
                "SKL-TCIA-05",
                {
                    "industry": industry,
                    "target_demographics": self._extract_demographics(personas),
                    "platforms": ["tiktok", "twitter", "reddit"],
                },
                ctx,
            ),
        ]
        research_results = await asyncio.gather(
            *research_tasks, return_exceptions=True
        )

        # Unpack research results
        social_trends = self._extract_data(research_results, 0, "social_trends")
        cultural_shifts = self._extract_data(research_results, 1, "cultural_shifts")
        viral_patterns = self._extract_data(research_results, 2, "viral_patterns")
        generational_insights = self._extract_data(
            research_results, 3, "generational_insights"
        )
        language_trends = self._extract_data(research_results, 4, "language_trends")

        # ── Step 5: Collect and cap trends (PG-08) ──
        all_trends = self._collect_all_trends(social_trends, cultural_shifts)
        if len(all_trends) > self._settings.MAX_TRENDS_PER_SESSION:
            all_trends = all_trends[: self._settings.MAX_TRENDS_PER_SESSION]

        # ── Step 6: Analysis phase (sequential) ──

        # SKL-TCIA-07: Cultural Relevance Scoring
        scoring_result = await self._execute_skill(
            "SKL-TCIA-07",
            {
                "trends": all_trends,
                "personas": personas,
                "competitor_landscape": competitor_context,
                "market_context": market_context,
                "brand_context": config,
            },
            ctx,
        )
        scored_trends = scoring_result.data.get("scored_trends", [])

        # SKL-TCIA-08: Trend-Persona Mapping
        mapping_result = await self._execute_skill(
            "SKL-TCIA-08",
            {
                "scored_trends": scored_trends,
                "personas": personas,
                "generational_insights": generational_insights,
            },
            ctx,
        )
        trend_persona_matrix = mapping_result.data.get(
            "trend_persona_matrix", {"mappings": []}
        )

        # SKL-TCIA-09: Opportunity Alert Generation
        alert_threshold = config.get(
            "alert_threshold", self._settings.ALERT_THRESHOLD
        )
        alert_result = await self._execute_skill(
            "SKL-TCIA-09",
            {
                "scored_trends": scored_trends,
                "trend_persona_matrix": trend_persona_matrix,
                "alert_threshold": alert_threshold,
            },
            ctx,
        )
        alerts = alert_result.data.get("opportunity_alerts", [])

        # PG-09: Alert throttle
        alerts = await self._throttle_alerts(alerts, tenant_id)

        # SKL-TCIA-10: Trend Report Synthesis
        report_result = await self._execute_skill(
            "SKL-TCIA-10",
            {
                "scored_trends": scored_trends,
                "trend_persona_matrix": trend_persona_matrix,
                "alerts": alerts,
                "viral_patterns": viral_patterns,
                "cultural_shifts": cultural_shifts,
                "generational_insights": generational_insights,
                "language_trends": language_trends,
                "report_type": config.get("scan_type", "on_demand"),
                "rag_context": rag_context,
            },
            ctx,
        )
        report = report_result.data.get("trend_report", {})

        # ── Step 7: Output guardrails ──
        await self._guardrails.validate_output(
            report, scored_trends, alerts, tenant_id
        )

        # ── Step 8: Persist (SKL-TCIA-11) ──
        persist_result = await self._execute_skill(
            "SKL-TCIA-11",
            {
                "report": report,
                "scored_trends": scored_trends,
                "alerts": alerts,
                "tenant_id": tenant_id,
            },
            ctx,
        )

        # ── Step 9: Update trend registry ──
        for trend in scored_trends:
            slug = trend.get("trend_slug", "")
            if slug:
                await self._trend_registry.upsert_trend(tenant_id, slug, trend)

        # ── Step 10: Collect sources ──
        sources = self._collect_sources(research_results)

        return {
            "trend_report": report,
            "scored_trends": scored_trends,
            "trend_persona_matrix": trend_persona_matrix,
            "opportunity_alerts": alerts,
            "viral_patterns": viral_patterns,
            "cultural_shifts": cultural_shifts,
            "generational_insights": generational_insights,
            "language_trends": language_trends,
            "sources": sources,
            "findings": self._extract_findings(report),
            "recommendations": report.get("strategic_recommendations", []),
            "confidence_score": report.get("confidence_score", 0.0),
            "report_url": persist_result.data.get("report_url", ""),
        }

    async def _execute_skill(
        self,
        skill_id: str,
        input_data: dict[str, Any],
        context: SkillContext,
    ) -> SkillResult:
        """Execute a single skill with error handling."""
        skill = self._skills.get_skill(skill_id)
        if not skill:
            logger.warning("Skill %s not found", skill_id)
            return SkillResult(
                skill_id=skill_id, success=False, error="Skill not found"
            )
        try:
            return await skill.execute(input_data, context)
        except Exception as exc:
            logger.error("Skill %s failed: %s", skill_id, exc)
            return SkillResult(
                skill_id=skill_id, success=False, error=str(exc)
            )

    async def _bounded_skill(
        self,
        semaphore: asyncio.Semaphore,
        skill_id: str,
        input_data: dict[str, Any],
        context: SkillContext,
    ) -> SkillResult:
        """Execute a skill within a concurrency-bounded semaphore."""
        async with semaphore:
            return await self._execute_skill(skill_id, input_data, context)

    async def _throttle_alerts(
        self,
        alerts: list[dict[str, Any]],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        """PG-09: Throttle alerts to max per tenant per day."""
        max_alerts = self._settings.MAX_ALERTS_PER_DAY
        current_count = await self._redis.get_alert_count(tenant_id)
        remaining = max(0, max_alerts - current_count)
        if remaining == 0:
            logger.info("PG-09: Alert throttle hit for tenant %s", tenant_id)
            return []
        throttled = alerts[:remaining]
        for _ in throttled:
            await self._redis.increment_alert_count(tenant_id)
        return throttled

    @staticmethod
    def _extract_industry(
        market_context: dict[str, Any], prompt: str
    ) -> str:
        """Extract industry from market context or prompt."""
        if market_context:
            overview = market_context.get("market_overview", {})
            if isinstance(overview, dict):
                industry = overview.get("industry", "")
                if industry:
                    return industry
        # Fallback: use prompt keywords
        return prompt[:100]

    @staticmethod
    def _extract_persona_keywords(personas: list[dict]) -> list[str]:
        """Extract keywords from APA personas."""
        keywords = []
        for p in personas[:5]:
            label = p.get("segment_label", "")
            if label:
                keywords.extend(label.split()[:3])
        return keywords[:10]

    @staticmethod
    def _extract_persona_platforms(personas: list[dict]) -> list[str]:
        """Extract preferred platforms from personas."""
        platforms = set()
        for p in personas[:5]:
            media = p.get("media_habits", {})
            if isinstance(media, dict):
                for platform in media.get("preferred_channels", []):
                    platforms.add(platform.lower())
        return list(platforms) or ["twitter", "tiktok", "instagram"]

    @staticmethod
    def _extract_age_ranges(personas: list[dict]) -> list[str]:
        """Extract age ranges from personas."""
        ranges = []
        for p in personas[:5]:
            demo = p.get("demographics", {})
            if isinstance(demo, dict):
                age = demo.get("age_range", "")
                if age:
                    ranges.append(age)
        return ranges

    @staticmethod
    def _extract_demographics(personas: list[dict]) -> list[str]:
        """Extract demographic labels from personas."""
        labels = []
        for p in personas[:5]:
            label = p.get("segment_label", "")
            if label:
                labels.append(label)
        return labels

    @staticmethod
    def _collect_all_trends(
        social_trends: list[dict], cultural_shifts: list[dict]
    ) -> list[dict[str, Any]]:
        """Combine social trends and cultural shifts into a unified list."""
        all_trends: list[dict[str, Any]] = []
        for t in social_trends:
            all_trends.append(
                {
                    "topic": t.get("topic", ""),
                    "platform": t.get("platform", ""),
                    "velocity_score": t.get("velocity_score", 0),
                    "type": "social",
                }
            )
        for c in cultural_shifts:
            all_trends.append(
                {
                    "topic": c.get("shift_description", c.get("domain", ""))[:200],
                    "domain": c.get("domain", ""),
                    "evidence_strength": c.get("evidence_strength", 0),
                    "type": "cultural",
                }
            )
        return all_trends

    @staticmethod
    def _extract_data(
        results: list[Any], index: int, key: str
    ) -> Any:
        """Safely extract data from gathered research results."""
        if index >= len(results):
            return [] if key != "viral_patterns" and key != "language_trends" else {}
        result = results[index]
        if isinstance(result, Exception):
            logger.warning("Research task %d failed: %s", index, result)
            return [] if key != "viral_patterns" and key != "language_trends" else {}
        if isinstance(result, SkillResult):
            return result.data.get(key, [] if key not in ("viral_patterns", "language_trends") else {})
        return [] if key != "viral_patterns" and key != "language_trends" else {}

    @staticmethod
    def _collect_sources(results: list[Any]) -> list[dict[str, str]]:
        """Collect sources from all research results."""
        sources: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for result in results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, SkillResult) and result.success:
                for key in ("social_trends", "cultural_shifts"):
                    items = result.data.get(key, [])
                    for item in items:
                        if isinstance(item, dict):
                            urls = item.get("sample_content_urls", [])
                            for url in urls:
                                if url and url not in seen_urls:
                                    seen_urls.add(url)
                                    sources.append(
                                        {
                                            "type": "web",
                                            "title": item.get("topic", ""),
                                            "url": url,
                                        }
                                    )
                            # Cultural shift sources
                            for src in item.get("sources", []):
                                if isinstance(src, dict):
                                    url = src.get("url", "")
                                    if url and url not in seen_urls:
                                        seen_urls.add(url)
                                        sources.append(
                                            {
                                                "type": "web",
                                                "title": src.get("title", ""),
                                                "url": url,
                                            }
                                        )
        return sources

    @staticmethod
    def _extract_findings(report: dict[str, Any]) -> list[str]:
        """Extract key findings from the trend report."""
        findings = []
        summary = report.get("executive_summary", "")
        if summary:
            findings.append(summary[:500])
        new_trends = report.get("new_trends", [])
        if new_trends:
            findings.append(f"New trends identified: {', '.join(new_trends[:5])}")
        rising = report.get("rising_trends", [])
        if rising:
            findings.append(f"Rising trends: {', '.join(rising[:5])}")
        return findings or ["Trend analysis completed."]
