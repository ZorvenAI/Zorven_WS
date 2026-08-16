"""SKL-OIA-04 — Map a finalized transcript batch onto approved questions.

Design §8.1 · implemented by story G-02.

The skill receives a window of redacted, finalized segments and the current
question list. It asks Gemini to classify which questions are being answered,
identifies ad-hoc questions the operator asked that were not prepared, and
surfaces notable facts.

Evidence spans use ``{recording_id, t_start, t_end}`` — the ``Question.evidence``
shape from Design §10.1 — so downstream stories (G-03 green signals, G-06
coverage checklist, I-03 playback deep-linking) can cite the exact moment.
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
You are an onboarding meeting analyst. You receive a batch of redacted \
transcript segments and a list of prepared questions.

Your job:
1. Determine which prepared questions (if any) are being answered in the \
transcript batch.
2. Identify any ad-hoc questions the operator asked that are NOT in the \
prepared list.
3. Surface notable facts about the business that may be useful.

RULES:
- Only map a segment to a question if the transcript content is clearly \
relevant to that question.
- Each attachment must include evidence spans with the recording_id, t_start, \
and t_end from the segments that support the mapping.
- Set relevance between 0.0 and 1.0 indicating how directly the transcript \
answers the question.
- If the batch does not answer any prepared question, return an empty \
attachments array.
- Return valid JSON only, no markdown fences, no extra text.

OUTPUT FORMAT (JSON):
{
  "attachments": [
    {
      "question_id": "<id of the prepared question>",
      "relevance": 0.85,
      "evidence": [{"recording_id": "r_01", "t_start": 120.5, "t_end": 123.8}]
    }
  ],
  "adhoc_questions": [
    {
      "text": "<the question that was asked>",
      "t_start": 125.0,
      "inferred_target_field": "<best-guess Company field>"
    }
  ],
  "notable_facts": [
    {
      "text": "<the fact>",
      "suggested_field": "<best-guess Company field>"
    }
  ]
}
"""


class AnalyzeTranscriptStream(StreamingSkill):
    """Map a finalized transcript batch onto approved questions.

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
        segments = context.input_context.get("segments", [])
        questions = context.input_context.get("question_states", [])
        recording_id = context.input_context.get("recording_id", "")

        if not segments:
            return

        if self._llm is None:
            raise LLMUnavailable("no LLM provider configured for SKL-OIA-04")

        prompt = self._build_prompt(segments, questions, recording_id)
        response = await self._llm.generate(prompt, temperature=0.1)
        parsed = self._parse_response(response, recording_id, segments)

        for attachment in parsed.get("attachments", []):
            yield {"type": "attachment", **attachment}
        for adhoc in parsed.get("adhoc_questions", []):
            yield {"type": "adhoc_question", **adhoc}
        for fact in parsed.get("notable_facts", []):
            yield {"type": "notable_fact", **fact}

    @staticmethod
    def _build_prompt(
        segments: list[dict[str, Any]],
        questions: list[dict[str, Any]],
        recording_id: str,
    ) -> str:
        lines = [_SYSTEM_PROMPT, "", "PREPARED QUESTIONS:"]
        for q in questions:
            qid = q.get("id", "")
            text = q.get("text", "")
            target = q.get("target_field", "")
            status = q.get("status", "OPEN")
            lines.append(f"  [{qid}] ({status}) {text}")
            if target:
                lines.append(f"    target_field: {target}")

        lines.append("")
        lines.append(f"RECORDING: {recording_id}")
        lines.append("")
        lines.append("TRANSCRIPT BATCH:")
        for seg in segments:
            t0 = seg.get("t_start", 0.0)
            t1 = seg.get("t_end", 0.0)
            speaker = seg.get("speaker", 0)
            text = seg.get("text", "")
            lines.append(f"  [{t0:.1f}-{t1:.1f}] Speaker {speaker}: {text}")

        lines.append("")
        lines.append("Respond with JSON only.")
        return "\n".join(lines)

    @staticmethod
    def _parse_response(
        response: str,
        recording_id: str,
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Parse the LLM response, falling back to empty on bad JSON."""
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
            logger.warning("skl_oia_04_bad_json", extra_len=len(response))
            return {"attachments": [], "adhoc_questions": [], "notable_facts": []}

        if not isinstance(parsed, dict):
            return {"attachments": [], "adhoc_questions": [], "notable_facts": []}

        for att in parsed.get("attachments", []):
            if not isinstance(att, dict):
                continue
            evidence = att.get("evidence")
            if not isinstance(evidence, list):
                att["evidence"] = [
                    {
                        "recording_id": recording_id,
                        "t_start": segments[0].get("t_start", 0.0) if segments else 0.0,
                        "t_end": segments[-1].get("t_end", 0.0) if segments else 0.0,
                    }
                ]
            else:
                for ev in evidence:
                    if isinstance(ev, dict) and "recording_id" not in ev:
                        ev["recording_id"] = recording_id

        return parsed
