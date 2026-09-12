"""SKL-OIA-05 — Score whether a prepared question has been answered sufficiently.

Design §8.1 · implemented by story G-03.

The skill receives a single question with its accumulated evidence spans and
scores 0.0–1.0 how completely the question has been answered.  When the score
meets the threshold a green flag is raised; otherwise ``missing_aspects``
lists what the answer still lacks so G-04 can generate follow-ups.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from app.core.logging import get_logger
from app.providers.llm import LLMProvider, LLMUnavailable
from app.skills.base import StreamingSkill
from app.skills.models import SkillContext

logger = get_logger(__name__)

_SYSTEM_PROMPT = """\
You are an onboarding meeting analyst scoring answer sufficiency.

You receive:
1. A prepared question about a business.
2. The target field this question maps to.
3. Transcript evidence spans that may answer the question.

Your job: score from 0.0 to 1.0 how completely the evidence answers the \
question, and list any aspects that remain unanswered.

SCORING GUIDE:
- 1.0: The question is fully and unambiguously answered with specific details.
- 0.7-0.9: The question is substantially answered but minor details are missing.
- 0.4-0.6: A partial answer exists but key aspects are missing.
- 0.1-0.3: The evidence only tangentially relates to the question.
- 0.0: No relevant answer exists in the evidence.

RULES:
- Score only what the evidence explicitly says. Do not infer or assume.
- If the evidence is empty, score 0.0.
- missing_aspects should list concrete things the answer did not cover.
- Return valid JSON only, no markdown fences, no extra text.

OUTPUT FORMAT (JSON):
{
  "score": 0.85,
  "missing_aspects": ["founding year not mentioned", "co-founders not named"]
}
"""


class EvaluateAnswerSufficiency(StreamingSkill):
    """Score whether a prepared question has been answered sufficiently.

    Streaming: output guardrails run per yielded chunk, not once at the end.
    """

    def __init__(
        self,
        meta: Any,
        *,
        llm: LLMProvider | None = None,
    ) -> None:
        super().__init__(meta)
        self._llm = llm

    async def stream(self, context: SkillContext) -> AsyncIterator[dict[str, Any]]:
        question = context.input_context.get("question", "")
        spans = context.input_context.get("attached_spans", [])
        target_field = context.input_context.get("target_field", "")
        threshold = context.config.get("sufficiency_green_threshold", 0.7)

        if not spans:
            yield {
                "type": "sufficiency_result",
                "sufficiency_score": 0.0,
                "green": False,
                "missing_aspects": ["no evidence spans available"],
                "evidence": [],
            }
            return

        if self._llm is None:
            raise LLMUnavailable("no LLM provider configured for SKL-OIA-05")

        prompt = self._build_prompt(question, spans, target_field)
        response = await self._llm.generate(prompt, temperature=0.1)
        result = self._parse_response(response)

        score = result["score"]
        evidence = [
            {
                "recording_id": s.get("recording_id", ""),
                "t_start": s.get("t_start", 0.0),
                "t_end": s.get("t_end", 0.0),
            }
            for s in spans
            if s.get("recording_id")
        ]

        yield {
            "type": "sufficiency_result",
            "sufficiency_score": score,
            "green": score >= threshold,
            "missing_aspects": result.get("missing_aspects", []),
            "evidence": evidence,
        }

    @staticmethod
    def _build_prompt(
        question: str,
        spans: list[dict[str, Any]],
        target_field: str,
    ) -> str:
        lines = [_SYSTEM_PROMPT, "", f"QUESTION: {question}"]
        if target_field:
            lines.append(f"TARGET FIELD: {target_field}")
        lines.append("")
        lines.append("EVIDENCE SPANS:")
        for span in spans:
            rid = span.get("recording_id", "?")
            t0 = span.get("t_start", 0.0)
            t1 = span.get("t_end", 0.0)
            text = span.get("text", "")
            lines.append(f"  [{rid} {t0:.1f}-{t1:.1f}] {text}")
        lines.append("")
        lines.append("Respond with JSON only.")
        return "\n".join(lines)

    @staticmethod
    def _parse_response(response: str) -> dict[str, Any]:
        """Parse the LLM response, falling back to score 0 on bad JSON."""
        cleaned = response.strip()
        if cleaned.startswith("```"):
            first_nl = cleaned.index("\n") if "\n" in cleaned else 3
            cleaned = cleaned[first_nl + 1 :]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning("skl_oia_05_bad_json", extra_len=len(response))
            return {"score": 0.0, "missing_aspects": ["LLM response unparseable"]}

        if not isinstance(parsed, dict):
            return {"score": 0.0, "missing_aspects": ["LLM response not a dict"]}

        score = parsed.get("score", 0.0)
        if not isinstance(score, (int, float)):
            score = 0.0
        score = max(0.0, min(1.0, float(score)))
        parsed["score"] = score

        aspects = parsed.get("missing_aspects", [])
        if not isinstance(aspects, list):
            parsed["missing_aspects"] = []
        else:
            parsed["missing_aspects"] = [str(a) for a in aspects if a]

        return parsed
