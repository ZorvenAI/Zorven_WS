"""SKL-TCIA-08: Trend-Persona Mapper.

Maps scored trends to APA personas with affinity scores and content angles.
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_MAPPING_PROMPT = """You are a brand strategist. Map each trend to each persona, generating affinity scores and content angles.

## Input
Scored trends: {scored_trends}
Personas: {personas}
Generational insights: {generational_insights}

## Output Format (JSON object)
{{
  "mappings": [
    {{
      "trend_slug": "trend-slug",
      "persona_slug": "persona-slug",
      "affinity_score": 0.85,
      "content_angles": ["angle 1", "angle 2"],
      "customer_segment_overlap": 0.7,
      "recommended_channels": ["tiktok", "instagram"]
    }}
  ]
}}

Return ONLY a valid JSON object. No markdown, no explanation."""


class TrendPersonaMapper(BaseSkill):
    """Map trends to personas with affinity scores."""

    meta = SkillMeta(
        skill_id="SKL-TCIA-08",
        name="trend_persona_mapper",
        description="Map trends to APA personas with affinity and content angles",
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

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        start = time.monotonic()

        scored_trends = input_data.get("scored_trends", [])
        personas = input_data.get("personas", [])
        generational_insights = input_data.get("generational_insights", [])

        if not self._anthropic or not personas:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={"trend_persona_matrix": {"mappings": []}},
                duration_ms=(time.monotonic() - start) * 1000,
            )

        if self._prompt_loader:
            from app.prompts.fallbacks import FALLBACK_PERSONA_MAPPING

            prompt = await self._prompt_loader.load(
                "zorven-wf1-tcia-persona-mapping",
                tenant_id=context.tenant_id or None,
                variables={
                    "scored_trends": json.dumps(
                        scored_trends[:15], default=str
                    )[:3000],
                    "context.scored_trends": json.dumps(
                        scored_trends[:15], default=str
                    )[:3000],
                    "personas": json.dumps(personas[:5], default=str)[:2000],
                    "context.personas": json.dumps(personas[:5], default=str)[:2000],
                    "generational_insights": json.dumps(
                        generational_insights[:4], default=str
                    )[:2000],
                    "context.generational_insights": json.dumps(
                        generational_insights[:4], default=str
                    )[:2000],
                },
                fallback=FALLBACK_PERSONA_MAPPING,
            )
        else:
            prompt = _MAPPING_PROMPT.format(
                scored_trends=json.dumps(scored_trends[:15], default=str)[:3000],
                personas=json.dumps(personas[:5], default=str)[:2000],
                generational_insights=json.dumps(
                    generational_insights[:4], default=str
                )[:2000],
            )

        try:
            llm_kwargs = dict(
                model="claude-sonnet-5",
                max_tokens=4096,
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
            matrix = self._parse_json_response(text)
            tokens_used = (
                response.usage.input_tokens + response.usage.output_tokens
            )
        except Exception as exc:
            logger.warning("Trend-persona mapping failed: %s", exc)
            matrix = {"mappings": []}
            tokens_used = 0

        elapsed = (time.monotonic() - start) * 1000
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={"trend_persona_matrix": matrix},
            duration_ms=elapsed,
            tokens_used=tokens_used,
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
            return {"mappings": []}
        except json.JSONDecodeError:
            logger.warning("Failed to parse trend-persona matrix JSON")
            return {"mappings": []}
