"""SKL-MRA-03: Market Analysis Synthesis — LLM-powered analysis via Claude."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYNTHESIS_SYSTEM = """\
You are a senior market research analyst. Synthesize the provided raw data into a \
structured analysis.

Analysis types:
- "landscape": Competitive landscape analysis (competitors, market shares, positioning)
- "sizing": Market sizing with TAM/SAM/SOM estimates
- "segmentation": Market segmentation breakdown
- "trends": Industry trend analysis and forecasting

Respond with a JSON object containing:
- "analysis": string — the main analysis narrative (2-3 paragraphs)
- "findings": list of key finding strings (5-10 items, factual and data-backed)
- "recommendations": list of actionable recommendations (3-5 items)
- "confidence_score": float 0.0-1.0
- "citations": list of {"claim": str, "source": str} objects

Only output valid JSON, no other text."""


class MarketAnalysisSynthesis(BaseSkill):
    """Synthesizes raw data into structured market analysis via Claude."""

    meta = SkillMeta(
        skill_id="SKL-MRA-03",
        name="market_analysis_synthesis",
        description="LLM synthesis of raw data into structured market analysis",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
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
        Synthesize raw data into analysis.

        input_data keys:
          - raw_data (str): Raw context to analyze
          - analysis_type (str): landscape|sizing|segmentation|trends
          - tenant_context (dict): Tenant-specific context
          - prompt (str): Original user prompt
        """
        start = time.monotonic()
        raw_data = input_data.get("raw_data", "")
        analysis_type = input_data.get("analysis_type", "landscape")
        prompt = input_data.get("prompt", "")

        if not raw_data:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No raw data provided for synthesis",
                duration_ms=_elapsed(start),
            )

        # Stub mode when no Anthropic client
        if self._client is None:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "analysis": f"Stub analysis for: {prompt[:100]}",
                    "findings": [f"Analysis pending for: {prompt[:50]}"],
                    "recommendations": ["Configure API key for real synthesis."],
                    "confidence_score": 0.3,
                    "citations": [],
                    "analysis_type": analysis_type,
                },
                duration_ms=_elapsed(start),
            )

        try:
            skill_hint = context.skill_context_text or ""
            system = _SYNTHESIS_SYSTEM
            if skill_hint:
                system += f"\n\nAdditional context:\n{skill_hint[:2000]}"

            user_msg = (
                f"Research query: {prompt}\n"
                f"Analysis type: {analysis_type}\n\n"
                f"Raw data:\n{raw_data[:30000]}"
            )

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )

            tokens_used = getattr(message, "usage", None)
            token_count = 0
            if tokens_used:
                token_count = getattr(tokens_used, "input_tokens", 0) + getattr(
                    tokens_used, "output_tokens", 0
                )

            content = message.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            synthesis = json.loads(content)
            synthesis["analysis_type"] = analysis_type

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=synthesis,
                duration_ms=_elapsed(start),
                tokens_used=token_count,
            )
        except Exception as exc:
            logger.warning("MarketAnalysisSynthesis failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
