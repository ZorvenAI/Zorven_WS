"""SKL-TCIA-10: Trend Report Synthesizer.

Compiles comprehensive trend report with scorecard and strategic recommendations.
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYNTHESIS_PROMPT = """You are a senior brand strategist synthesizing a trend intelligence report.

## Input Data
Scored trends: {scored_trends}
Trend-persona matrix: {persona_matrix}
Alerts: {alerts}
Viral patterns: {viral_patterns}
Cultural shifts: {cultural_shifts}
Generational insights: {generational_insights}
Language trends: {language_trends}
Report type: {report_type}
RAG historical context: {rag_context}

## Output Format (JSON object)
{{
  "executive_summary": "2-3 paragraph executive summary of key findings",
  "trend_scorecard": [],
  "new_trends": ["trend names appearing for the first time"],
  "rising_trends": ["trends gaining momentum"],
  "fading_trends": ["trends losing relevance"],
  "competitive_trend_gaps": ["trends competitors miss that the brand can exploit"],
  "strategic_recommendations": ["actionable recommendation 1", "recommendation 2"],
  "confidence_score": 0.85,
  "citations": ["url1", "url2"]
}}

Return ONLY a valid JSON object. No markdown, no explanation."""


class TrendReportSynthesizer(BaseSkill):
    """Synthesize comprehensive trend report via Claude."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-10",
        name="trend_report_synthesizer",
        description="Synthesize comprehensive trend report with strategic recommendations",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=90000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self, anthropic_client: Any = None, cb_llm: Any = None
    ) -> None:
        self._anthropic = anthropic_client
        self._cb_llm = cb_llm

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()

        if not self._anthropic:
            return self._stub_result(input_data, start)

        prompt = _SYNTHESIS_PROMPT.format(
            scored_trends=json.dumps(
                input_data.get("scored_trends", [])[:15], default=str
            )[:3000],
            persona_matrix=json.dumps(
                input_data.get("trend_persona_matrix", {}), default=str
            )[:2000],
            alerts=json.dumps(
                input_data.get("alerts", [])[:5], default=str
            )[:1000],
            viral_patterns=json.dumps(
                input_data.get("viral_patterns", {}), default=str
            )[:1000],
            cultural_shifts=json.dumps(
                input_data.get("cultural_shifts", [])[:5], default=str
            )[:2000],
            generational_insights=json.dumps(
                input_data.get("generational_insights", [])[:4], default=str
            )[:2000],
            language_trends=json.dumps(
                input_data.get("language_trends", {}), default=str
            )[:1000],
            report_type=input_data.get("report_type", "on_demand"),
            rag_context=json.dumps(
                input_data.get("rag_context", {}), default=str
            )[:1000],
        )

        try:
            llm_kwargs = dict(
                model="claude-sonnet-4-5-20250929",
                max_tokens=8192,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            if self._cb_llm:
                response = await self._cb_llm.call(
                    self._anthropic.messages.create, **llm_kwargs
                )
            else:
                response = await self._anthropic.messages.create(**llm_kwargs)
            text = response.content[0].text.strip()
            report = self._parse_json_response(text)
            tokens_used = (
                response.usage.input_tokens + response.usage.output_tokens
            )
        except Exception as exc:
            logger.warning("Trend report synthesis failed: %s", exc)
            return self._stub_result(input_data, start)

        # Ensure scored trends are included in the report
        if not report.get("trend_scorecard"):
            report["trend_scorecard"] = input_data.get("scored_trends", [])

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"trend_report": report},
            duration_ms=elapsed,
            tokens_used=tokens_used,
        )

    def _stub_result(
        self, input_data: dict[str, Any], start: float
    ) -> SkillResult:
        """Stub result when LLM is unavailable."""
        scored = input_data.get("scored_trends", [])
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "trend_report": {
                    "executive_summary": (
                        "Trend analysis completed (stub mode). "
                        f"{len(scored)} trends identified."
                    ),
                    "trend_scorecard": scored,
                    "new_trends": [],
                    "rising_trends": [],
                    "fading_trends": [],
                    "competitive_trend_gaps": [],
                    "strategic_recommendations": [
                        "Review identified trends for brand relevance."
                    ],
                    "confidence_score": 0.5,
                    "citations": [],
                }
            },
            duration_ms=(time.monotonic() - start) * 1000,
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from LLM response."""
        if "```" in text:
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
            return {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse trend report JSON")
            return {
                "executive_summary": text[:2000],
                "trend_scorecard": [],
                "new_trends": [],
                "rising_trends": [],
                "fading_trends": [],
                "competitive_trend_gaps": [],
                "strategic_recommendations": [],
                "confidence_score": 0.5,
                "citations": [],
            }
