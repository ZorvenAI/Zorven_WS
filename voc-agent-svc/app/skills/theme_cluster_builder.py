"""SKL-VoCA-10: Theme Cluster Builder.

Hierarchical theme clustering using Claude Sonnet 4:
- Top-level themes with sub-themes
- Per-theme feedback count, sentiment distribution, severity score
- Representative quotes (anonymized)
- Correlates with CIA competitor weaknesses and MRA market context
"""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Voice of Customer theme analysis specialist. Cluster customer \
feedback into hierarchical themes using unsupervised categorization.

## Clustering Rules

1. Identify **top-level themes** (3-10) from the feedback corpus.
2. For each top-level theme, identify **sub-themes** (1-5).
3. For each theme and sub-theme, compute:
   - feedback_count: number of feedback items belonging to this cluster
   - sentiment: positive/neutral/negative distribution (floats 0.0-1.0, sum to 1.0)
   - severity_score: float 0.0-10.0 (10 = critical business impact)
4. Include **representative_quotes** (2-5 per theme) — anonymize all customer \
identifiers (names, emails, IDs). Replace with "[Customer]" or "[User]".
5. Assign a **theme_slug** (URL-safe, lowercase, hyphenated).

## Cross-Agent Correlation

When competitor intelligence (CIA) data is available:
- Set **competitor_correlation** on each theme: describe how competitors handle \
the same issue. Note competitor weaknesses that align with the theme.

When market research (MRA) data is available:
- Set **market_context** on each theme: relate the theme to market trends or \
segment dynamics.

If CIA or MRA data is absent, set the respective fields to empty strings.

## Input Data
Brand/company: {brand_query}
Feedback data: {feedback_data}
CIA competitor context: {cia_context}
MRA market context: {mra_context}
Skill context: {skill_context}

## Output (JSON)
{{
  "themes": [
    {{
      "theme_slug": "product-quality",
      "theme_name": "Product Quality",
      "feedback_count": 120,
      "severity_score": 7.5,
      "sentiment": {{"positive": 0.2, "neutral": 0.3, "negative": 0.5}},
      "sub_themes": [
        {{
          "name": "Durability Issues",
          "feedback_count": 45,
          "sentiment": {{"positive": 0.1, "neutral": 0.2, "negative": 0.7}},
          "representative_quotes": ["[Customer] reported...", "..."]
        }}
      ],
      "representative_quotes": ["[Customer] said...", "..."],
      "competitor_correlation": "Competitor X has similar issues...",
      "market_context": "Industry trend toward..."
    }}
  ],
  "total_feedback_analyzed": 500,
  "clustering_method": "llm_hierarchical"
}}

Return ONLY valid JSON. No markdown, no explanation."""


class ThemeClusterBuilder(BaseSkill):
    """Hierarchical theme clustering with cross-agent correlation."""

    meta = SkillMeta(
        skill_id="SKL-VoCA-10",
        name="theme_cluster_builder",
        description=(
            "Hierarchical theme clustering: top-level themes with sub-themes, "
            "feedback counts, sentiment distributions, severity scores, "
            "anonymized representative quotes, CIA competitor correlation, "
            "and MRA market context."
        ),
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=90000,
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

    async def execute(
        self, input_data: dict[str, Any], context: SkillContext
    ) -> SkillResult:
        """Execute theme clustering on aggregated feedback data.

        input_data keys:
          - prompt (str): Brand/company query
          - feedback_data (dict): Aggregated feedback from collection skills
        context.previous_outputs may contain:
          - competitor_intelligence (dict): CIA data for competitor correlation
          - market_research (dict): MRA data for market context
        """
        start = time.monotonic()
        prompt = input_data.get("prompt", "")
        feedback_data = input_data.get("feedback_data", {})

        # Extract upstream agent context
        prev = context.previous_outputs or {}
        cia_context = prev.get("competitor_intelligence", {})
        mra_context = prev.get("market_research", {})

        if self._client is None:
            return self._stub_result(start)

        try:
            skill_context_text = context.skill_context_text or ""
            if self._prompt_loader:
                from app.prompts.fallbacks import FALLBACK_THEME_CLUSTERING

                system_msg = await self._prompt_loader.load(
                    "zorven-wf1-voca-theme-clustering",
                    tenant_id=context.tenant_id or None,
                    variables={
                        "brand_query": prompt[:500],
                        "context.brand_query": prompt[:500],
                        "feedback_data": json.dumps(
                            feedback_data, default=str
                        )[:12000],
                        "context.feedback_data": json.dumps(
                            feedback_data, default=str
                        )[:12000],
                        "cia_context": json.dumps(
                            cia_context, default=str
                        )[:3000],
                        "context.cia_context": json.dumps(
                            cia_context, default=str
                        )[:3000],
                        "mra_context": json.dumps(
                            mra_context, default=str
                        )[:3000],
                        "context.mra_context": json.dumps(
                            mra_context, default=str
                        )[:3000],
                        "skill_context": skill_context_text[:1500],
                        "context.skill_context": skill_context_text[:1500],
                    },
                    fallback=FALLBACK_THEME_CLUSTERING,
                )
            else:
                system_msg = _SYSTEM_PROMPT.format(
                    brand_query=prompt[:500],
                    feedback_data=json.dumps(feedback_data, default=str)[:12000],
                    cia_context=json.dumps(cia_context, default=str)[:3000],
                    mra_context=json.dumps(mra_context, default=str)[:3000],
                    skill_context=skill_context_text[:1500],
                )

            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking={"type": "disabled"},
                system=system_msg,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Cluster feedback themes for: {prompt}\n\n"
                            f"Total feedback items: "
                            f"{feedback_data.get('total_items', 'unknown')}"
                        ),
                    }
                ],
            ) as _stream:
                response = await _stream.get_final_message()

            text = next(b.text for b in response.content if b.type == "text").strip()
            parsed = self._parse_json_response(text)
            tokens_used = self._count_tokens(response)

            elapsed = (time.monotonic() - start) * 1000

            theme_count = len(parsed.get("themes", []))
            logger.info(
                "SKL-VoCA-10 completed: themes=%d, total_feedback=%d, "
                "tokens=%d, duration=%.0fms",
                theme_count,
                parsed.get("total_feedback_analyzed", 0),
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
            logger.warning("Theme clustering failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _stub_result(self, start: float) -> SkillResult:
        """Return stub theme data when the LLM client is unavailable."""
        return SkillResult(
            skill_id=self.meta.skill_id,
            success=True,
            data={
                "themes": [],
                "total_feedback_analyzed": 0,
                "clustering_method": "stub",
                "message": "STUB MODE: VOCA_ANTHROPIC_API_KEY is not configured on this deployment.",
            },
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
            result = json.loads(text, strict=False)
            if isinstance(result, dict):
                return result
            return {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse theme cluster JSON")
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
