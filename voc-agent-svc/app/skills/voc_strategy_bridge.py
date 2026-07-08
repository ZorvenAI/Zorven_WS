"""SKL-VoCA-12: VoC Strategy Bridge Synthesizer.

Capstone skill that cross-references all VoC data with upstream agents
(MRA, CIA, APA, TCIA) using Claude Sonnet 4 to produce:
- Pain point priority matrix (severity, frequency, persona impact,
  competitor gaps, trend alignment)
- VoC health score (0-100, weighted composite)
- Strategic recommendations and Odoo onboarding guidance
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Voice of Customer strategist. Synthesize all VoC analysis \
data into an actionable strategy bridge document that connects customer \
feedback insights to business strategy.

## Input Data Sources

1. **Sentiment Analysis** (SKL-VoCA-09): Overall/channel/persona sentiment, \
emotion profile, trend direction.
2. **Theme Clusters** (SKL-VoCA-10): Hierarchical themes with severity scores, \
competitor correlation, market context.
3. **NPS Analysis** (SKL-VoCA-11): NPS scores, trends, drivers, detractor themes.
4. **Market Research (MRA)**: Market sizing, TAM/SAM/SOM, industry trends.
5. **Competitor Intelligence (CIA)**: Competitor profiles, SWOT, benchmarking.
6. **Audience Personas (APA)**: Buyer personas, demographics, psychographics.
7. **Trend & Cultural Insights (TCIA)**: Cultural trends, relevance scores.

## Pain Point Priority Matrix

Rank pain points by composite score:
- **severity** (float 0.0-10.0): Business impact severity
- **frequency** (int): How often this pain point appears in feedback
- **persona_impact** (list[str]): Which personas are affected
- **competitor_gap** (str): Whether competitors solve this better/worse
- **trend_alignment** (str): Whether market trends amplify or mitigate this
- **recommended_action** (str): Specific actionable recommendation

Methodology: "composite_weighted" — severity * 0.3 + frequency_norm * 0.25 + \
persona_breadth * 0.2 + competitor_gap_score * 0.15 + trend_alignment_score * 0.1

## VoC Health Score (0-100)

Weighted composite:
- NPS component ({nps_weight}%): Normalize NPS (-100 to +100) → (0-100)
- Sentiment component ({sentiment_weight}%): Overall positive sentiment * 100
- Theme resolution component ({theme_weight}%): % of themes with severity < 5.0

Health score weights are tenant-configurable. Apply the weights provided.

**External-Only Mode cap**: If operating_mode="external_only", cap the health \
score at 70 maximum (data confidence penalty).

## Odoo Onboarding Recommendation

If operating_mode="external_only", populate odoo_onboarding_recommendation with \
a specific recommendation about which Odoo modules (Helpdesk, Surveys, etc.) \
would most improve VoC data quality and unlock the full health score.

If operating_mode="full", set odoo_onboarding_recommendation to empty string.

## Input
Brand/company: {brand_query}
Operating mode: {operating_mode}
Sentiment data: {sentiment_data}
Theme data: {theme_data}
NPS data: {nps_data}
MRA context: {mra_context}
CIA context: {cia_context}
APA context: {apa_context}
TCIA context: {tcia_context}
Health score weights: NPS={nps_weight}%, Sentiment={sentiment_weight}%, \
Theme Resolution={theme_weight}%
Skill context: {skill_context}

## Output (JSON)
{{
  "executive_summary": "2-3 paragraph strategic summary",
  "pain_point_priority_matrix": {{
    "pain_points": [
      {{
        "name": "Pain point name",
        "severity": 8.5,
        "frequency": 120,
        "persona_impact": ["Enterprise Decision Maker", "SMB Owner"],
        "competitor_gap": "Competitor X solves this with...",
        "trend_alignment": "Market trend toward... amplifies this",
        "recommended_action": "Specific action to take"
      }}
    ],
    "methodology": "composite_weighted"
  }},
  "voc_health_score": 65.0,
  "voc_health_breakdown": {{
    "nps_component": 0.0,
    "sentiment_component": 0.0,
    "theme_resolution_component": 0.0
  }},
  "operating_mode": "external_only",
  "odoo_onboarding_recommendation": "Connecting Odoo Helpdesk would...",
  "cross_agent_insights": {{
    "mra": "Market research indicates...",
    "cia": "Competitor analysis shows...",
    "apa": "Persona data reveals...",
    "tcia": "Cultural trends suggest..."
  }},
  "strategic_recommendations": [
    "Recommendation 1",
    "Recommendation 2"
  ]
}}

Return ONLY valid JSON. No markdown, no explanation."""


class VoCStrategyBridge(BaseSkill):
    """Capstone VoC-to-strategy bridge synthesizer."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-12",
        name="voc_strategy_bridge",
        description=(
            "Capstone skill: cross-references all VoC data with MRA, CIA, "
            "APA, TCIA to produce pain point priority matrix, VoC health "
            "score (0-100, tenant-configurable weights), strategic "
            "recommendations, and Odoo onboarding guidance."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=120000,
        circuit_breaker_dependency="llm",
    )

    # Default weights matching config.py defaults
    DEFAULT_NPS_WEIGHT: float = 0.50
    DEFAULT_SENTIMENT_WEIGHT: float = 0.25
    DEFAULT_THEME_WEIGHT: float = 0.25

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.3,
        max_tokens: int = 16384,
        settings: Any = None,
        prompt_loader: Any = None,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._settings = settings
        self._prompt_loader = prompt_loader

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """Execute VoC strategy bridge synthesis.

        input_data keys:
          - prompt (str): Brand/company query
          - sentiment_data (dict): SKL-VoCA-09 output
          - theme_data (dict): SKL-VoCA-10 output
          - nps_data (dict): SKL-VoCA-11 output
        context.previous_outputs may contain:
          - market_research (dict): MRA data
          - competitor_intelligence (dict): CIA data
          - audience_persona (dict): APA data
          - trend_cultural_insights (dict): TCIA data
        context.config may contain:
          - voc_health_nps_weight (float): NPS weight override
          - voc_health_sentiment_weight (float): Sentiment weight override
          - voc_health_theme_weight (float): Theme resolution weight override
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        sentiment_data = input_data.get("sentiment_data", {})
        theme_data = input_data.get("theme_data", {})
        nps_data = input_data.get("nps_data", {})
        operating_mode = context.operating_mode or "external_only"

        # Extract upstream agent context
        prev = context.previous_outputs or {}
        mra_context = prev.get("market_research", {})
        cia_context = prev.get("competitor_intelligence", {})
        apa_context = prev.get("audience_persona", {})
        tcia_context = prev.get("trend_cultural_insights", {})

        # Resolve health score weights (tenant config > settings > defaults)
        cfg = context.config or {}
        nps_w = self._resolve_weight(
            cfg,
            "voc_health_nps_weight",
            "VOC_HEALTH_NPS_WEIGHT",
            self.DEFAULT_NPS_WEIGHT,
        )
        sent_w = self._resolve_weight(
            cfg,
            "voc_health_sentiment_weight",
            "VOC_HEALTH_SENTIMENT_WEIGHT",
            self.DEFAULT_SENTIMENT_WEIGHT,
        )
        theme_w = self._resolve_weight(
            cfg,
            "voc_health_theme_weight",
            "VOC_HEALTH_THEME_WEIGHT",
            self.DEFAULT_THEME_WEIGHT,
        )

        if self._client is None:
            return self._stub_result(operating_mode, nps_w, sent_w, theme_w, start)

        try:
            skill_context_text = context.skill_context_text or ""
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_STRATEGY_BRIDGE

                system_msg = await self._prompt_loader.load(
                    "zorven-wf1-voca-strategy-bridge",
                    tenant_id=context.tenant_id or None,
                    variables={
                        "brand_query": prompt[:500],
                        "operating_mode": operating_mode,
                        "sentiment_data": json.dumps(
                            sentiment_data, default=str
                        )[:5000],
                        "theme_data": json.dumps(
                            theme_data, default=str
                        )[:5000],
                        "nps_data": json.dumps(
                            nps_data, default=str
                        )[:3000],
                        "mra_context": json.dumps(
                            mra_context, default=str
                        )[:3000],
                        "cia_context": json.dumps(
                            cia_context, default=str
                        )[:3000],
                        "apa_context": json.dumps(
                            apa_context, default=str
                        )[:3000],
                        "tcia_context": json.dumps(
                            tcia_context, default=str
                        )[:3000],
                        "nps_weight": str(int(nps_w * 100)),
                        "sentiment_weight": str(int(sent_w * 100)),
                        "theme_weight": str(int(theme_w * 100)),
                        "skill_context": skill_context_text[:1500],
                    },
                    fallback=FALLBACK_STRATEGY_BRIDGE,
                )
            else:
                system_msg = _SYSTEM_PROMPT.format(
                    brand_query=prompt[:500],
                    operating_mode=operating_mode,
                    sentiment_data=json.dumps(sentiment_data, default=str)[:5000],
                    theme_data=json.dumps(theme_data, default=str)[:5000],
                    nps_data=json.dumps(nps_data, default=str)[:3000],
                    mra_context=json.dumps(mra_context, default=str)[:3000],
                    cia_context=json.dumps(cia_context, default=str)[:3000],
                    apa_context=json.dumps(apa_context, default=str)[:3000],
                    tcia_context=json.dumps(tcia_context, default=str)[:3000],
                    nps_weight=int(nps_w * 100),
                    sentiment_weight=int(sent_w * 100),
                    theme_weight=int(theme_w * 100),
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
                            f"Synthesize VoC strategy bridge for: {prompt}\n\n"
                            f"Operating mode: {operating_mode}\n"
                            f"Health score weights: NPS={nps_w:.0%}, "
                            f"Sentiment={sent_w:.0%}, "
                            f"Theme Resolution={theme_w:.0%}"
                        ),
                    }
                ],
            )

            text = response.content[0].text.strip()
            parsed = self._parse_json_response(text)
            tokens_used = self._count_tokens(response)

            # Enforce operating mode constraints
            parsed["operating_mode"] = operating_mode
            if operating_mode == "external_only":
                health_score = parsed.get("voc_health_score", 0.0)
                parsed["voc_health_score"] = min(health_score, 70.0)
                if not parsed.get("odoo_onboarding_recommendation"):
                    parsed["odoo_onboarding_recommendation"] = (
                        "Connect Odoo Helpdesk and Surveys to unlock "
                        "internal feedback channels and full VoC health "
                        "scoring (currently capped at 70)."
                    )
            else:
                parsed["odoo_onboarding_recommendation"] = ""

            elapsed = (time.monotonic() - start) * 1000

            logger.info(
                "SKL-VoCA-12 completed: health_score=%.1f, mode=%s, "
                "pain_points=%d, tokens=%d, duration=%.0fms",
                parsed.get("voc_health_score", 0.0),
                operating_mode,
                len(
                    parsed.get("pain_point_priority_matrix", {}).get("pain_points", [])
                ),
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
            logger.error("VoC strategy bridge synthesis failed: %s", exc, exc_info=True)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _resolve_weight(
        self,
        cfg: dict[str, Any],
        config_key: str,
        settings_attr: str,
        default: float,
    ) -> float:
        """Resolve weight from context config, then settings, then default."""
        # Tenant-level config override
        val = cfg.get(config_key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
        # Service-level settings
        if self._settings is not None:
            val = getattr(self._settings, settings_attr, None)
            if val is not None:
                return float(val)
        return default

    def _stub_result(
        self,
        operating_mode: str,
        nps_w: float,
        sent_w: float,
        theme_w: float,
        start: float,
    ) -> SkillResult:
        """Return stub strategy bridge when LLM client is unavailable."""
        health_score = 0.0
        if operating_mode == "external_only":
            health_score = min(health_score, 70.0)

        data: dict[str, Any] = {
            "executive_summary": "",
            "pain_point_priority_matrix": {
                "pain_points": [],
                "methodology": "composite_weighted",
            },
            "voc_health_score": health_score,
            "voc_health_breakdown": {
                "nps_component": 0.0,
                "sentiment_component": 0.0,
                "theme_resolution_component": 0.0,
            },
            "operating_mode": operating_mode,
            "odoo_onboarding_recommendation": (
                "Connect Odoo Helpdesk and Surveys to unlock internal "
                "feedback channels and full VoC health scoring."
                if operating_mode == "external_only"
                else ""
            ),
            "cross_agent_insights": {},
            "strategic_recommendations": [],
            "message": "LLM not available — strategy bridge skipped",
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
            logger.warning("Failed to parse VoC strategy bridge JSON")
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
