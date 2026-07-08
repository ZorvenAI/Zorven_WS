"""SKL-TCIA-07: Cultural Relevance Scorer.

4-dimension scoring (0-100) using Claude Sonnet 4:
- Audience Alignment (0-25)
- Competitive Landscape (0-25)
- Brand Fit (0-25)
- Momentum (0-25)
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SCORING_PROMPT = """You are a cultural trends analyst. Score each trend on 4 dimensions (0-25 each, total 0-100).

## Dimensions
1. **Audience Alignment** (0-25): How well does this trend overlap with the target audience personas?
2. **Competitive Landscape** (0-25): Is this trend being exploited or ignored by competitors?
3. **Brand Fit** (0-25): How well does this trend align with the brand's values and positioning?
4. **Momentum** (0-25): What is the trend's velocity and projected longevity?

## Recommendation Rules
- Score >= 75: "capitalize" (act now)
- Score 50-74: "monitor" (watch closely)
- Score < 50: "avoid" (not worth pursuing)

## Input
Trends: {trends}
Personas: {personas}
Competitor landscape: {competitors}
Market context: {market}

## Output Format (JSON array)
[
  {{
    "trend_slug": "slug-here",
    "topic": "Trend name",
    "relevance_score": 82,
    "audience_alignment": 22,
    "competitive_landscape": 20,
    "brand_fit": 21,
    "momentum": 19,
    "recommendation": "capitalize",
    "rationale": "Brief rationale",
    "citations": ["url1", "url2"],
    "platforms": ["tiktok", "instagram"]
  }}
]

Return ONLY a valid JSON array. No markdown, no explanation."""


class CulturalRelevanceScorer(BaseSkill):
    """Score trends on 4-dimension cultural relevance (0-100)."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-07",
        name="cultural_relevance_scorer",
        description="4-dimension cultural relevance scoring via Claude",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        cb_llm: Any = None,
        prompt_loader: Any = None,
    ) -> None:
        self._anthropic = anthropic_client
        self._cb_llm = cb_llm
        self._prompt_loader = prompt_loader
        self._odoo_client: Any = None
        self._redis: Any = None

    def set_odoo_client(self, odoo_client: Any, redis_manager: Any) -> None:
        """Inject optional Odoo CRM data source."""
        self._odoo_client = odoo_client
        self._redis = redis_manager

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()

        if not self._anthropic:
            logger.warning(
                "STUB MODE: TCIA_ANTHROPIC_API_KEY is not configured"
            )
            return self._stub_result(input_data, start)

        trends = input_data.get("trends", [])
        personas = input_data.get("personas", [])
        competitors = input_data.get("competitor_landscape", {})
        market = input_data.get("market_context", {})

        if self._prompt_loader:
            from app.prompts.fallbacks import FALLBACK_SCORING

            prompt = await self._prompt_loader.load(
                "zorven-wf1-tcia-scoring",
                tenant_id=context.tenant_id or None,
                variables={
                    "trends": json.dumps(trends[:25], default=str)[:4000],
                    "context.trends": json.dumps(trends[:25], default=str)[:4000],
                    "personas": json.dumps(personas[:5], default=str)[:2000],
                    "context.personas": json.dumps(personas[:5], default=str)[:2000],
                    "competitors": json.dumps(competitors, default=str)[:2000],
                    "context.competitors": json.dumps(competitors, default=str)[:2000],
                    "market": json.dumps(market, default=str)[:2000],
                    "context.market": json.dumps(market, default=str)[:2000],
                },
                fallback=FALLBACK_SCORING,
            )
        else:
            prompt = _SCORING_PROMPT.format(
                trends=json.dumps(trends[:25], default=str)[:4000],
                personas=json.dumps(personas[:5], default=str)[:2000],
                competitors=json.dumps(competitors, default=str)[:2000],
                market=json.dumps(market, default=str)[:2000],
            )

        try:
            llm_kwargs = dict(
                model="claude-sonnet-5",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            if self._cb_llm:
                response = await self._cb_llm.call(
                    self._anthropic.messages.create, **llm_kwargs
                )
            else:
                response = await self._anthropic.messages.create(**llm_kwargs)
            text = response.content[0].text.strip()
            scored_trends = self._parse_json_response(text)
            tokens_used = (
                response.usage.input_tokens + response.usage.output_tokens
            )
        except Exception as exc:
            logger.warning("Cultural relevance scoring failed: %s", exc)
            return self._stub_result(input_data, start)

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"scored_trends": scored_trends},
            duration_ms=elapsed,
            tokens_used=tokens_used,
        )

    def _stub_result(
        self, input_data: dict[str, Any], start: float
    ) -> SkillResult:
        """Return stub scored trends when LLM is unavailable."""
        trends = input_data.get("trends", [])
        stub_scored = []
        for i, t in enumerate(trends[:10]):
            topic = t.get("topic", t.get("shift_description", f"Trend {i + 1}"))
            slug = topic.lower().replace(" ", "-")[:50]
            stub_scored.append(
                {
                    "trend_slug": slug,
                    "topic": topic,
                    "relevance_score": 50,
                    "audience_alignment": 12,
                    "competitive_landscape": 13,
                    "brand_fit": 12,
                    "momentum": 13,
                    "recommendation": "monitor",
                    "rationale": "STUB MODE: TCIA_ANTHROPIC_API_KEY is not configured on this deployment.",
                    "citations": [],
                    "platforms": [],
                }
            )
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"scored_trends": stub_scored},
            duration_ms=(time.monotonic() - start) * 1000,
        )

    @staticmethod
    def _parse_json_response(text: str) -> list[dict[str, Any]]:
        """Parse JSON from LLM response, handling markdown fences."""
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
            if isinstance(result, list):
                return result
            return []
        except json.JSONDecodeError:
            logger.warning("Failed to parse scored trends JSON")
            return []
