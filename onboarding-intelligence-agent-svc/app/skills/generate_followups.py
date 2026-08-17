"""SKL-OIA-06 — Suggest follow-up questions for a partially answered question.

Design §8.1 · implemented by story G-04.

The skill receives a question with its missing_aspects (from SKL-OIA-05) and
generates at most three targeted follow-up questions that address specific gaps.
Follow-ups reference what the answer actually missed rather than restating the
original question in different words.
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
You are an onboarding meeting assistant generating follow-up questions.

You receive:
1. A prepared question about a business.
2. Aspects of the answer that are still missing.
3. The conversation tone to match.
4. Questions already asked (do not repeat these).

Your job: generate 1–3 SHORT follow-up questions that address specific gaps \
in the answer. Each follow-up must target a concrete missing aspect.

RULES:
- At most 3 follow-ups. Fewer is better if fewer gaps remain.
- Each follow-up must address a SPECIFIC missing aspect, not restate the \
original question in different words.
- Match the conversation tone. Keep questions natural and conversational.
- Do NOT repeat any question from the already_asked list.
- Do NOT ask questions that were already answered in the evidence.
- Return valid JSON only, no markdown fences, no extra text.

OUTPUT FORMAT (JSON array):
[
  {"text": "Can you recall the year you started?", \
"addresses_aspect": "founding year", "priority": 1},
  {"text": "Who else was involved at the beginning?", \
"addresses_aspect": "co-founders", "priority": 2}
]

Priority 1 = most important gap, 2 = next, 3 = least.
"""


class GenerateFollowups(StreamingSkill):
    """Suggest follow-up questions for a partially answered question.

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
        missing = context.input_context.get("missing_aspects", [])
        tone = context.input_context.get("conversation_tone", "professional")
        already = context.input_context.get("already_asked", [])

        if not missing:
            return

        if self._llm is None:
            raise LLMUnavailable("no LLM provider configured for SKL-OIA-06")

        prompt = self._build_prompt(question, missing, tone, already)
        response = await self._llm.generate(prompt, temperature=0.4)
        followups = self._parse_response(response)

        yield {
            "type": "followup_suggestions",
            "suggestions": followups[:3],
        }

    @staticmethod
    def _build_prompt(
        question: str,
        missing_aspects: list[str],
        tone: str,
        already_asked: list[str],
    ) -> str:
        lines = [
            _SYSTEM_PROMPT,
            "",
            f"ORIGINAL QUESTION: {question}",
            "",
            "MISSING ASPECTS:",
        ]
        for aspect in missing_aspects:
            lines.append(f"  - {aspect}")
        lines.append("")
        lines.append(f"CONVERSATION TONE: {tone}")
        if already_asked:
            lines.append("")
            lines.append("ALREADY ASKED (do not repeat):")
            for q in already_asked:
                lines.append(f"  - {q}")
        lines.append("")
        lines.append("Respond with a JSON array only.")
        return "\n".join(lines)

    @staticmethod
    def _parse_response(response: str) -> list[dict[str, Any]]:
        """Parse the LLM response, falling back to empty list on bad JSON."""
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
            logger.warning("skl_oia_06_bad_json", extra_len=len(response))
            return []

        if not isinstance(parsed, list):
            return []

        result: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            text = item.get("text", "")
            if not text or not isinstance(text, str):
                continue
            result.append(
                {
                    "text": str(text).strip(),
                    "addresses_aspect": str(item.get("addresses_aspect", "")).strip(),
                    "priority": int(item.get("priority", len(result) + 1)),
                }
            )

        result.sort(key=lambda f: f.get("priority", 99))
        return result
