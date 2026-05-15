"""SKL-VoCA-11: NPS Trend Analyzer.

NPS longitudinal analysis using Claude Sonnet 4:
- Full Mode: NPS from Odoo survey data with longitudinal trends and driver decomposition
- External-Only Mode: nps_available=false, proxy NPS derived from review star ratings
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Net Promoter Score (NPS) analyst. Analyze NPS data and \
compute trend analysis, driver decomposition, and detractor theme identification.

## Operating Modes

### Full Mode (operating_mode="full")
- Compute NPS from Odoo survey data (promoters: 9-10, passives: 7-8, detractors: 0-6).
- NPS = ((promoters - detractors) / total_responses) * 100, range -100 to +100.
- Set nps_available=true.
- Compute longitudinal trends across available time periods.
- Decompose NPS drivers (what's pushing scores up or down).
- Identify top detractor themes.
- Set data_source="odoo_survey".

### External-Only Mode (operating_mode="external_only")
- Set nps_available=false.
- Derive a **proxy NPS** from review star ratings:
  - 5 stars → promoter, 4 stars → passive, 1-3 stars → detractor
- Populate proxy_nps with the breakdown.
- Set current_nps to zeros.
- Include a caveat that this is proxy data with lower confidence.
- Set data_source="review_proxy".

## Input Data
Brand/company: {brand_query}
Operating mode: {operating_mode}
Survey data (Odoo NPS responses): {survey_data}
Review data (star ratings): {review_data}
Historical NPS (if any): {historical_nps}
Skill context: {skill_context}

## Output (JSON)
{{
  "nps_available": true,
  "current_nps": {{
    "promoters": 0,
    "passives": 0,
    "detractors": 0,
    "nps_score": 0.0,
    "total_responses": 0
  }},
  "proxy_nps": null,
  "trend_periods": [
    {{
      "period": "2025-Q4",
      "nps_score": 45.0,
      "promoters": 50,
      "passives": 30,
      "detractors": 20,
      "total_responses": 100
    }}
  ],
  "drivers": ["Fast delivery", "Product quality"],
  "detractor_themes": ["Poor support", "Pricing concerns"],
  "data_source": "odoo_survey"
}}

When nps_available=false, set proxy_nps to the breakdown object instead of null, \
and set current_nps scores to 0.

Return ONLY valid JSON. No markdown, no explanation."""


class NPSTrendAnalyzer(BaseSkill):
    """NPS trend analysis with full and external-only modes."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-11",
        name="nps_trend_analyzer",
        description=(
            "NPS trend analysis: Full mode uses Odoo survey data for "
            "longitudinal trends and driver decomposition. External-Only "
            "mode derives proxy NPS from review star ratings."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.3,
        max_tokens: int = 16384,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """Execute NPS trend analysis.

        input_data keys:
          - prompt (str): Brand/company query
          - survey_data (dict): Odoo NPS survey responses (full mode)
          - review_data (dict): Star rating review data (external-only mode)
          - historical_nps (dict): Previous NPS data for trend comparison
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        survey_data = input_data.get("survey_data", {})
        review_data = input_data.get("review_data", {})
        historical_nps = input_data.get("historical_nps", {})
        operating_mode = context.operating_mode or "external_only"

        if self._client is None:
            return self._stub_result(operating_mode, start)

        try:
            skill_context_text = context.skill_context_text or ""
            system_msg = _SYSTEM_PROMPT.format(
                brand_query=prompt[:500],
                operating_mode=operating_mode,
                survey_data=json.dumps(survey_data, default=str)[:8000],
                review_data=json.dumps(review_data, default=str)[:5000],
                historical_nps=json.dumps(historical_nps, default=str)[:3000],
                skill_context=skill_context_text[:1500],
            )

            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_msg,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Analyze NPS trends for: {prompt}\n\n"
                            f"Operating mode: {operating_mode}\n"
                            f"Survey responses available: "
                            f"{bool(survey_data)}\n"
                            f"Review data available: {bool(review_data)}"
                        ),
                    }
                ],
            )

            text = response.content[0].text.strip()
            parsed = self._parse_json_response(text)
            tokens_used = self._count_tokens(response)

            # Enforce operating mode constraints
            if operating_mode == "external_only":
                parsed["nps_available"] = False
                parsed["data_source"] = "review_proxy"
                # Zero out current_nps in external-only mode
                if "current_nps" in parsed:
                    parsed["current_nps"] = {
                        "promoters": 0,
                        "passives": 0,
                        "detractors": 0,
                        "nps_score": 0.0,
                        "total_responses": 0,
                    }

            elapsed = (time.monotonic() - start) * 1000

            logger.info(
                "SKL-VoCA-11 completed: nps_available=%s, mode=%s, "
                "tokens=%d, duration=%.0fms",
                parsed.get("nps_available", False),
                operating_mode,
                tokens_used,
                elapsed,
            )

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=parsed,
                duration_ms=elapsed,
                tokens_used=tokens_used,
            )

        except Exception as exc:
            logger.warning("NPS trend analysis failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _stub_result(self, operating_mode: str, start: float) -> SkillResult:
        """Return stub NPS data when the LLM client is unavailable."""
        nps_available = operating_mode != "external_only"
        data_source = "odoo_survey" if nps_available else "review_proxy"

        data: dict[str, Any] = {
            "nps_available": nps_available,
            "current_nps": {
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
                "nps_score": 0.0,
                "total_responses": 0,
            },
            "proxy_nps": None,
            "trend_periods": [],
            "drivers": [],
            "detractor_themes": [],
            "data_source": data_source,
            "message": "LLM not available — NPS analysis skipped",
        }

        if not nps_available:
            data["proxy_nps"] = {
                "promoters": 0,
                "passives": 0,
                "detractors": 0,
                "nps_score": 0.0,
                "total_responses": 0,
            }

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data=data,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code fences."""
        if "```" in text:
            lines = text.split("\n")
            json_lines: list[str] = []
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
            logger.warning("Failed to parse NPS trend analysis JSON")
            return {}

    @staticmethod
    def _count_tokens(response: Any) -> int:
        """Extract token count from Anthropic message response."""
        usage = getattr(response, "usage", None)
        if usage:
            return getattr(usage, "input_tokens", 0) + getattr(
                usage, "output_tokens", 0
            )
        return 0
