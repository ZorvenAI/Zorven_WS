"""SKL-VoCA-09: Sentiment Analyzer.

Multi-dimensional sentiment analysis using Claude Sonnet 4:
- Overall sentiment distribution (positive / neutral / negative)
- Per-channel sentiment with data provenance labelling
- Per-persona sentiment mapping
- Trend direction over time
- Emotion detection (Plutchik 8-emotion model)
- Data coverage scoring (0-100%)
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Voice of Customer sentiment analyst. Perform multi-dimensional \
sentiment analysis on customer feedback data across multiple channels.

## Analysis Dimensions

1. **Overall Sentiment**: Aggregate positive/neutral/negative distribution (floats 0.0-1.0, must sum to 1.0).
2. **Per-Channel Sentiment**: Break down sentiment by feedback channel. For each channel, include:
   - channel: channel identifier
   - provenance: "internal" (Odoo helpdesk/survey/chatter), "external" (reviews/social/forums), or "not_connected"
   - sentiment: positive/neutral/negative distribution
   - feedback_count: number of feedback items analyzed
   - confidence: float 0.0-1.0
3. **Per-Persona Sentiment**: Map sentiment to audience personas (from upstream APA data). \
Each persona key maps to a positive/neutral/negative distribution.
4. **Trend Direction**: One of "improving", "stable", "declining", or "insufficient_data".
5. **Emotion Profile** (Plutchik model): joy, trust, surprise, anticipation, anger, fear, sadness, disgust \
(floats 0.0-1.0, should roughly sum to 1.0).
6. **Data Coverage Score**: Percentage (0-100) of channels contributing meaningful data. \
Channels marked "not_connected" do not contribute.

## Channel List
- odoo_helpdesk (internal)
- odoo_survey (internal)
- odoo_chatter (internal)
- reviews (external)
- social_media (external)
- forums (external)
- rag_historical (external)

## Operating Mode
If operating_mode is "external_only", mark all Odoo channels (odoo_helpdesk, odoo_survey, \
odoo_chatter) as provenance="not_connected" with feedback_count=0.

## Input Data
Brand/company: {brand_query}
Operating mode: {operating_mode}
Feedback data: {feedback_data}
Persona context: {persona_context}
Skill context: {skill_context}

## Output (JSON)
{{
  "overall_sentiment": {{"positive": 0.0, "neutral": 0.0, "negative": 0.0}},
  "emotion_profile": {{
    "joy": 0.0, "trust": 0.0, "surprise": 0.0, "anticipation": 0.0,
    "anger": 0.0, "fear": 0.0, "sadness": 0.0, "disgust": 0.0
  }},
  "channel_sentiments": [
    {{
      "channel": "reviews",
      "provenance": "external",
      "sentiment": {{"positive": 0.0, "neutral": 0.0, "negative": 0.0}},
      "feedback_count": 0,
      "confidence": 0.0
    }}
  ],
  "persona_sentiments": {{"Persona Label": {{"positive": 0.0, "neutral": 0.0, "negative": 0.0}}}},
  "trend_direction": "stable",
  "data_coverage_score": 0.0
}}

Return ONLY valid JSON. No markdown, no explanation."""


class SentimentAnalyzer(BaseSkill):
    """Multi-dimensional sentiment analysis with data provenance tracking."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-09",
        name="sentiment_analyzer",
        description=(
            "Multi-dimensional sentiment analysis: overall, per-channel, "
            "per-persona, trend over time, emotion detection. Computes "
            "data coverage score and labels channel provenance."
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

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """Execute sentiment analysis on aggregated feedback data.

        input_data keys:
          - prompt (str): Brand/company query
          - feedback_data (dict): Aggregated feedback from collection skills
          - persona_context (dict): APA persona data from previous_outputs
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        feedback_data = input_data.get("feedback_data", {})
        persona_context = input_data.get("persona_context", {})
        operating_mode = context.operating_mode or "external_only"

        if self._client is None:
            return self._stub_result(operating_mode, start)

        try:
            skill_context_text = context.skill_context_text or ""
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_SENTIMENT

                system_msg = await self._prompt_loader.load(
                    "zorven-wf1-voca-sentiment-analysis",
                    tenant_id=context.tenant_id or None,
                    variables={
                        "brand_query": prompt[:500],
                        "context.brand_query": prompt[:500],
                        "operating_mode": operating_mode,
                        "context.operating_mode": operating_mode,
                        "feedback_data": json.dumps(
                            feedback_data, default=str
                        )[:12000],
                        "context.feedback_data": json.dumps(
                            feedback_data, default=str
                        )[:12000],
                        "persona_context": json.dumps(
                            persona_context, default=str
                        )[:3000],
                        "context.persona_context": json.dumps(
                            persona_context, default=str
                        )[:3000],
                        "skill_context": skill_context_text[:1500],
                        "context.skill_context": skill_context_text[:1500],
                    },
                    fallback=FALLBACK_SENTIMENT,
                )
            else:
                system_msg = _SYSTEM_PROMPT.format(
                    brand_query=prompt[:500],
                    operating_mode=operating_mode,
                    feedback_data=json.dumps(feedback_data, default=str)[:12000],
                    persona_context=json.dumps(persona_context, default=str)[:3000],
                    skill_context=skill_context_text[:1500],
                )

            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system_msg,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Analyze sentiment for: {prompt}\n\n"
                            f"Operating mode: {operating_mode}"
                        ),
                    }
                ],
            )

            text = next(b.text for b in response.content if b.type == "text").strip()
            parsed = self._parse_json_response(text)
            tokens_used = self._count_tokens(response)

            # Compute data_coverage_score from channel_sentiments
            channel_sentiments = parsed.get("channel_sentiments", [])
            coverage = self._compute_data_coverage(channel_sentiments)
            parsed["data_coverage_score"] = coverage

            # Label provenance for channels based on operating mode
            self._apply_provenance(channel_sentiments, operating_mode)

            elapsed = (time.monotonic() - start) * 1000

            logger.info(
                "SKL-VoCA-09 completed: coverage=%.1f%%, mode=%s, "
                "tokens=%d, duration=%.0fms",
                coverage,
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
            logger.warning("Sentiment analysis failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _stub_result(self, operating_mode: str, start: float) -> SkillResult:
        """Return stub sentiment data when the LLM client is unavailable."""
        internal_channels = ["odoo_helpdesk", "odoo_survey", "odoo_chatter"]
        external_channels = ["reviews", "social_media", "forums", "rag_historical"]

        channel_sentiments = []
        for ch in external_channels:
            channel_sentiments.append(
                {
                    "channel": ch,
                    "provenance": "external",
                    "sentiment": {
                        "positive": 0.33,
                        "neutral": 0.34,
                        "negative": 0.33,
                    },
                    "feedback_count": 0,
                    "confidence": 0.0,
                }
            )
        for ch in internal_channels:
            prov = "not_connected" if operating_mode == "external_only" else "internal"
            channel_sentiments.append(
                {
                    "channel": ch,
                    "provenance": prov,
                    "sentiment": {
                        "positive": 0.33,
                        "neutral": 0.34,
                        "negative": 0.33,
                    },
                    "feedback_count": 0,
                    "confidence": 0.0,
                }
            )

        coverage = self._compute_data_coverage(channel_sentiments)

        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "overall_sentiment": {
                    "positive": 0.33,
                    "neutral": 0.34,
                    "negative": 0.33,
                },
                "emotion_profile": {
                    "joy": 0.0,
                    "trust": 0.0,
                    "surprise": 0.0,
                    "anticipation": 0.0,
                    "anger": 0.0,
                    "fear": 0.0,
                    "sadness": 0.0,
                    "disgust": 0.0,
                },
                "channel_sentiments": channel_sentiments,
                "persona_sentiments": {},
                "trend_direction": "insufficient_data",
                "data_coverage_score": coverage,
                "message": "STUB MODE: VOCA_ANTHROPIC_API_KEY is not configured on this deployment.",
            },
            duration_ms=(time.monotonic() - start) * 1000,
        )

    @staticmethod
    def _compute_data_coverage(channel_sentiments: list[dict]) -> float:
        """Compute data coverage score (0-100) as % of contributing channels."""
        if not channel_sentiments:
            return 0.0
        total = len(channel_sentiments)
        contributing = sum(
            1
            for cs in channel_sentiments
            if cs.get("provenance") != "not_connected"
            and cs.get("feedback_count", 0) > 0
        )
        return round((contributing / total) * 100, 1)

    @staticmethod
    def _apply_provenance(channel_sentiments: list[dict], operating_mode: str) -> None:
        """Enforce provenance labels based on operating mode."""
        internal_channels = {"odoo_helpdesk", "odoo_survey", "odoo_chatter"}
        for cs in channel_sentiments:
            ch = cs.get("channel", "")
            if ch in internal_channels and operating_mode == "external_only":
                cs["provenance"] = "not_connected"
                cs["feedback_count"] = 0
                cs["confidence"] = 0.0

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
            logger.warning("Failed to parse sentiment analysis JSON")
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
