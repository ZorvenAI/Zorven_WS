"""SKL-CIA-10: Competitive Benchmarking Synthesizer — Final report via Claude."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_BENCHMARKING_SYSTEM_PROMPT = """\
You are a senior competitive intelligence strategist. Synthesize all competitor data \
into a comprehensive competitive benchmarking report.

The report must include:
1. **Executive Summary** — 2-3 paragraphs with key takeaways
2. **Competitor Matrix** — Comparative scores across 6-8 dimensions
3. **Key Findings** — Factual, evidence-backed insights
4. **Strategic Recommendations** — Actionable next steps ranked by impact
5. **Confidence Assessment** — Overall confidence in the analysis

Respond with JSON:
{
  "report": {
    "executive_summary": "...",
    "competitor_matrix": {
      "dimensions": ["product", "pricing", "support", "brand", "growth", "technology"],
      "scores": {"CompanyA": {"product": 8, "pricing": 6, ...}, ...}
    },
    "key_findings": ["...", "..."],
    "strategic_recommendations": [
      {"recommendation": "...", "impact": "high|medium|low", "effort": "high|medium|low"}
    ],
    "confidence_score": 0.8
  }
}

Only output valid JSON, no other text."""


class CompetitiveBenchmarkingSynthesizer(BaseSkill):
    """Synthesize all data into a final competitive benchmarking report."""

    meta = SkillMeta(
        skill_id="SKL-CIA-10",
        name="competitive_benchmarking_synthesizer",
        description=(
            "Final benchmarking report: executive summary, competitor matrix, "
            "key findings, strategic recommendations via Claude Sonnet 4."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=90000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Synthesize competitive benchmarking report.

        input_data keys:
          - raw_data (str): All compiled competitor data
          - prompt (str): Original query
          - market_context (dict): MRA context
        """
        start = time.monotonic()
        raw_data = input_data.get("raw_data", "")
        prompt = input_data.get("prompt", "")
        market_context = input_data.get("market_context", {})

        if not raw_data:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "report": "",
                    "summary": "No data for benchmarking report",
                },
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "report": f"Stub benchmarking report for: {prompt}",
                    "summary": "LLM not available — benchmarking synthesis skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            system = _BENCHMARKING_SYSTEM_PROMPT
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            user_message = f"Competitive intelligence query: {prompt}\n\n"
            if market_context:
                overview = market_context.get("market_overview", "")
                sizing = market_context.get("market_sizing", {})
                if overview:
                    user_message += f"Market overview:\n{overview[:800]}\n\n"
                if sizing:
                    user_message += f"Market sizing:\n{json.dumps(sizing)[:500]}\n\n"
            user_message += f"Full competitor data:\n{raw_data[:30000]}"

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            tokens_used = _count_tokens(message)
            content = _parse_json_response(message.content[0].text)
            report = content.get("report", content)

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "report": report if isinstance(report, str) else json.dumps(report),
                    "report_data": report if isinstance(report, dict) else content,
                    "summary": (
                        report.get("executive_summary", "")[:500]
                        if isinstance(report, dict)
                        else str(report)[:500]
                    ),
                },
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("Benchmarking synthesis failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _count_tokens(message: Any) -> int:
    usage = getattr(message, "usage", None)
    if usage:
        return getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
    return 0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
