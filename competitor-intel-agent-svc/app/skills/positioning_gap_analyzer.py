"""SKL-CIA-09: Positioning Gap Analyzer — Cross-competitor gap analysis via Claude."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_POSITIONING_SYSTEM_PROMPT = """\
You are a competitive positioning analyst. Analyze the competitor data to identify \
positioning gaps, white-space opportunities, and differentiation dimensions.

Build a positioning analysis including:
1. **Positioning Map**: 2D map with relevant axes (e.g., Price vs. Feature richness)
2. **Gap Identification**: Unserved segments, feature gaps, price gaps, channel gaps
3. **Opportunity Scoring**: Rate each gap 0-10 on attractiveness, feasibility, \
   defensibility, alignment

Respond with JSON:
{
  "positioning_map": {
    "x_axis": "...",
    "y_axis": "...",
    "positions": [{"competitor": "...", "x": 0.5, "y": 0.8}]
  },
  "positioning_gaps": [
    {
      "dimension": "...",
      "gap_description": "...",
      "opportunity_score": 8,
      "evidence": ["..."],
      "gap_type": "segment|feature|price|geographic|channel"
    }
  ],
  "differentiation_dimensions": [
    {"dimension": "...", "leader": "...", "laggard": "...", "gap_size": "large|medium|small"}
  ]
}

Only output valid JSON, no other text."""


class PositioningGapAnalyzer(BaseSkill):
    """Identify positioning gaps and white-space opportunities."""

    meta = SkillMeta(
        skill_id="SKL-CIA-09",
        name="positioning_gap_analyzer",
        description=(
            "Cross-competitor positioning analysis: gap identification, "
            "white-space opportunities, differentiation scoring via Claude."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-5",
        max_tokens: int = 32768,
        prompt_loader: Any = None,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.max_tokens = max_tokens
        self._prompt_loader = prompt_loader

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Analyze positioning gaps.

        input_data keys:
          - raw_data (str): Compiled competitor data
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
                    "positioning_gaps": [],
                    "positioning_map": {},
                    "differentiation_dimensions": [],
                    "message": "No data for positioning analysis",
                },
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "positioning_gaps": [],
                    "positioning_map": {},
                    "differentiation_dimensions": [],
                    "message": "LLM not available — positioning analysis skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_POSITIONING_GAP

                system = await self._prompt_loader.load(
                    "zorven-wf1-cia-positioning-gap",
                    tenant_id=context.tenant_id or None,
                    fallback=FALLBACK_POSITIONING_GAP,
                )
            else:
                system = _POSITIONING_SYSTEM_PROMPT
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            user_message = f"Analysis query: {prompt}\n\n"
            if market_context:
                trends = market_context.get("industry_trends", [])
                if trends:
                    user_message += f"Industry trends:\n{json.dumps(trends[:5])}\n\n"
            user_message += f"Competitor data:\n{raw_data[:25000]}"

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            tokens_used = _count_tokens(message)
            content = _parse_json_response(next(b.text for b in message.content if b.type == "text"))

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "positioning_gaps": content.get("positioning_gaps", []),
                    "positioning_map": content.get("positioning_map", {}),
                    "differentiation_dimensions": content.get(
                        "differentiation_dimensions", []
                    ),
                },
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("Positioning gap analysis failed: %s", exc)
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
    return json.loads(text, strict=False)


def _count_tokens(message: Any) -> int:
    usage = getattr(message, "usage", None)
    if usage:
        return getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
    return 0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
