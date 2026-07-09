"""SKL-CIA-08: SWOT Analysis Generator — Per-competitor SWOT via Claude Sonnet 4."""

import json
import logging
import time
from typing import Any, Optional

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SWOT_SYSTEM_PROMPT = """\
You are a competitive intelligence analyst. Generate a SWOT analysis for each \
competitor based on the provided evidence data.

For each competitor, produce:
- "strengths": list of strings (observable advantages backed by evidence)
- "weaknesses": list of strings (documented gaps with evidence)
- "opportunities": list of strings (market gaps they could exploit)
- "threats": list of strings (external risks they face)
- "confidence_score": float 0.0-1.0

Every SWOT item MUST cite at least one source from the evidence. Do not speculate \
without data.

Respond with JSON: {"swot_analyses": [{"competitor": "...", "slug": "...", \
"strengths": [...], "weaknesses": [...], "opportunities": [...], "threats": [...], \
"confidence_score": 0.8, "citations": [...]}]}

Only output valid JSON, no other text."""


class SWOTAnalysisGenerator(BaseSkill):
    """Generate per-competitor SWOT analyses grounded in evidence."""

    meta = SkillMeta(
        skill_id="SKL-CIA-08",
        name="swot_analysis_generator",
        description=(
            "Generate evidence-grounded SWOT analyses per competitor "
            "using Claude Sonnet 4. Every claim cites source URLs."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-5",
        max_tokens: int = 16384,
        prompt_loader: Any = None,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.max_tokens = max_tokens
        self._prompt_loader = prompt_loader

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Generate SWOT analyses.

        input_data keys:
          - raw_data (str): Compiled data from previous skills
          - prompt (str): Original query
          - market_context (dict): MRA context for enrichment
          - analysis_type (str): Type of analysis
        """
        start = time.monotonic()
        raw_data = input_data.get("raw_data", "")
        prompt = input_data.get("prompt", "")
        market_context = input_data.get("market_context", {})

        if not raw_data:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"swot_analyses": [], "message": "No data for SWOT analysis"},
                duration_ms=_elapsed(start),
            )

        if self._client is None:
            # Stub mode — return placeholder SWOT
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "swot_analyses": [],
                    "message": "LLM not available — SWOT analysis skipped",
                },
                duration_ms=_elapsed(start),
            )

        try:
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_SWOT

                system = await self._prompt_loader.load(
                    "zorven-wf1-cia-swot",
                    tenant_id=context.tenant_id or None,
                    fallback=FALLBACK_SWOT,
                )
            else:
                system = _SWOT_SYSTEM_PROMPT
            skill_context = context.skill_context_text
            if skill_context:
                system += f"\n\nMethodology:\n{skill_context[:1500]}"

            user_message = f"Analysis query: {prompt}\n\n"
            if market_context:
                overview = market_context.get("market_overview", "")
                if overview:
                    user_message += f"Market context:\n{overview[:800]}\n\n"
            user_message += f"Competitor evidence:\n{raw_data[:25000]}"

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )

            tokens_used = _count_tokens(message)
            content = _parse_json_response(next(b.text for b in message.content if b.type == "text"))
            swot_analyses = content.get("swot_analyses", [])

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"swot_analyses": swot_analyses},
                tokens_used=tokens_used,
                duration_ms=_elapsed(start),
            )
        except Exception as exc:
            logger.warning("SWOT generation failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _parse_json_response(text: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def _count_tokens(message: Any) -> int:
    """Extract token count from Anthropic message."""
    usage = getattr(message, "usage", None)
    if usage:
        return getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
    return 0


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
