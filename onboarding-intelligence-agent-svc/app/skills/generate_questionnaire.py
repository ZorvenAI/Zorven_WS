"""SKL-OIA-02 — Generate a questionnaire to the operator's count and depth.

Design §8.1 · implemented by story C-03.

Reads the C-02 brief from ``input_context``. Its ``open_unknowns`` are the
richest input here — C-02 prompted for them explicitly because this is what
turns them into questions — so they lead the prompt rather than sitting under
the established facts.

**Count is enforced in code, not asked for politely.** AC-1 says *exactly* 12,
and a model asked for twelve returns eleven or thirteen often enough that a
prompt instruction is not an implementation. Over-generation is trimmed and
under-generation is topped up from the unknowns, both in a way that protects
workflow coverage rather than just hitting the number.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.providers.llm import LLMProvider, LLMUnavailable
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult
from app.skills.questionnaire_models import (
    WORKFLOWS,
    GeneratedQuestion,
    GeneratedQuestionnaire,
)

logger = get_logger(__name__)

SKILL_ID = "SKL-OIA-02"

DEFAULT_COUNT = 10
MAX_COUNT = 40

#: What each depth asks the model for. The names match Django's DEPTH_NAMES so
#: the chat, the skill and the column agree on what "deep" means.
DEPTH_GUIDANCE = {
    "quick": (
        "Ask direct, factual questions that can be answered briefly. "
        "Cover ground rather than probing."
    ),
    "standard": (
        "Mix factual coverage with some probing. Where a fact matters, follow "
        "it with a question about why or how."
    ),
    "deep": (
        "Probe mechanism and evidence, not facts. Prefer 'why', 'how do you "
        "know', 'what would change your mind', 'walk me through'. A question "
        "answerable from their website is a wasted question — assume the "
        "researched facts below are already known."
    ),
}

PROMPT = """\
You are preparing questions for a brand onboarding meeting.

What research already established (do NOT ask these back):
{facts}

What research could NOT establish — these are the most valuable things to ask:
{unknowns}

Business: {company_name}
Operator's notes: {notes}

Generate exactly {count} questions. {depth_guidance}

Every question must carry:
  "text": the question, addressed to the business owner.
  "workflow_target": exactly one of "WF1", "WF2", "WF3".
      WF1 = discovery: market, customers, competitors, positioning inputs.
      WF2 = brand strategy: identity, personality, story, naming, values.
      WF3 = campaigns and creative: existing ads, business photography, brand
            assets already in use, past marketing that worked or failed,
            channels, budget, creative preferences.
  "target_field": one of the field names below if the answer would populate
      it, otherwise "". Do not invent names.

Allowed target_field values:
{vocabulary}

You MUST include at least {wf3_min} WF3 questions. Preparation is not scoped
to a brand-strategy interview: the meeting also has to collect what campaigns
and creative need, and that material is only obtainable by asking.

Return ONLY a JSON array of objects. No prose, no code fence.
"""


class GenerateQuestionnaire(BaseSkill):
    """Generate a questionnaire to the requested count and depth."""

    def __init__(
        self,
        meta: Any,
        *,
        llm: LLMProvider | None = None,
        vocabulary: list[str] | None = None,
    ) -> None:
        super().__init__(meta)
        self._llm = llm
        self._vocabulary = vocabulary or []

    def set_vocabulary(self, fields: list[str]) -> None:
        """Install the target_field names fetched from Django.

        Late-bound because the vocabulary is a network read the executor does
        once and caches, and a skill that fetched it per invocation would put
        a Django round trip inside every generation.
        """
        self._vocabulary = sorted(set(fields))

    async def run(self, context: SkillContext) -> SkillResult:
        hints = context.input_context or {}
        brief = hints.get("research_brief") or {}
        count = self._requested_count(hints)
        depth = self._requested_depth(hints)

        if self._llm is None:
            return self._degraded(count, depth, "no LLM is configured")

        try:
            raw = await self._llm.generate(
                self._prompt(brief, hints, count, depth),
                # Slightly warmer than research: a questionnaire of twelve
                # near-identical questions is a worse failure than an
                # imprecise one, and there is no factual claim to protect
                # here — the facts came from C-02.
                temperature=0.5,
            )
        except LLMUnavailable as exc:
            logger.warning("questionnaire_degraded", reason=exc.reason)
            return self._degraded(count, depth, exc.reason)

        questions = self._parse(raw)
        questions = self._enforce_count(questions, count, brief)

        result = GeneratedQuestionnaire(
            questions=questions,
            depth=depth,
            requested_count=count,
        )
        result.recompute_coverage()
        return SkillResult(skill_id=SKILL_ID, output=result.model_dump())

    # ── The request ──────────────────────────────────────────────────

    @staticmethod
    def _requested_count(hints: dict[str, Any]) -> int:
        """How many questions, clamped to something a meeting can hold.

        A model asked for 500 questions produces a wall of text and a large
        bill; a request for 0 produces nothing to approve. Both are more
        likely to be a client bug than an intention.
        """
        raw = hints.get("count", DEFAULT_COUNT)
        try:
            count = int(raw)
        except (TypeError, ValueError):
            return DEFAULT_COUNT
        if isinstance(raw, bool):
            return DEFAULT_COUNT
        return max(1, min(count, MAX_COUNT))

    @staticmethod
    def _requested_depth(hints: dict[str, Any]) -> str:
        depth = str(hints.get("depth") or "standard").strip().lower()
        return depth if depth in DEPTH_GUIDANCE else "standard"

    def _prompt(
        self, brief: dict[str, Any], hints: dict[str, Any], count: int, depth: str
    ) -> str:
        facts = [
            f"- {f.get('statement', '')}"
            for f in brief.get("facts", [])
            if isinstance(f, dict) and f.get("statement")
        ]
        unknowns = [f"- {u}" for u in brief.get("open_unknowns", []) if u]

        return PROMPT.format(
            facts="\n".join(facts) or "(none — research was unavailable)",
            unknowns="\n".join(unknowns) or "(none recorded)",
            company_name=brief.get("company_name")
            or hints.get("company_name")
            or "(unnamed)",
            notes=hints.get("operator_notes") or "(none)",
            count=count,
            depth_guidance=DEPTH_GUIDANCE[depth],
            vocabulary="\n".join(f"  {f}" for f in self._vocabulary)
            or '  (none available — use "" for every target_field)',
            # A floor rather than a share: on a small set a percentage rounds
            # to zero, which is exactly when WF3 goes missing.
            wf3_min=max(2, count // 5),
        )

    # ── Reading the model's answer ───────────────────────────────────

    def _parse(self, raw: str) -> list[GeneratedQuestion]:
        """Build questions from the model's JSON array, dropping what cannot
        be used.

        A question with an unknown workflow or no text is dropped rather than
        coerced: guessing WF1 for an unlabelled question would corrupt the
        coverage figure AC-3 asks the operator to act on.
        """
        text = raw.strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            logger.warning("questionnaire_completion_had_no_json_array")
            return []
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError:
            logger.warning("questionnaire_completion_was_not_valid_json")
            return []
        if not isinstance(parsed, list):
            return []

        allowed = set(self._vocabulary)
        questions: list[GeneratedQuestion] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            field = str(item.get("target_field") or "").strip()
            try:
                questions.append(
                    GeneratedQuestion(
                        text=str(item.get("text") or "").strip(),
                        workflow_target=str(item.get("workflow_target") or ""),
                        # Dropped here as well as at Django's boundary. Both
                        # matter: this keeps the coverage figure honest, and
                        # Django's stops a caller that is not this skill.
                        target_field=field if (not allowed or field in allowed) else "",
                    )
                )
            except ValueError:
                continue
        return questions

    # ── AC-1 · exactly the requested count ───────────────────────────

    def _enforce_count(
        self, questions: list[GeneratedQuestion], count: int, brief: dict[str, Any]
    ) -> list[GeneratedQuestion]:
        """Return exactly ``count`` questions.

        Trimming drops from the **most represented workflow first**, so
        cutting to size cannot be what removes WF3 — which would turn AC-1
        into a violation of AC-2. Topping up draws on the brief's unknowns,
        which are already the questions worth asking, and falls back to
        explicit WF3 asset prompts because that is the coverage most often
        short.
        """
        if len(questions) > count:
            return self._trim(questions, count)
        if len(questions) < count:
            return questions + self._top_up(questions, count - len(questions), brief)
        return questions

    @staticmethod
    def _trim(
        questions: list[GeneratedQuestion], count: int
    ) -> list[GeneratedQuestion]:
        kept = list(questions)
        while len(kept) > count:
            counts: dict[str, int] = {w: 0 for w in WORKFLOWS}
            for q in kept:
                counts[q.workflow_target] += 1
            fattest = max(WORKFLOWS, key=lambda w: counts[w])
            # Drop the last of the most-represented workflow; earlier
            # questions in a workflow tend to be its most central.
            for index in range(len(kept) - 1, -1, -1):
                if kept[index].workflow_target == fattest:
                    kept.pop(index)
                    break
            else:  # pragma: no cover - unreachable while counts are derived
                kept.pop()
        return kept

    @staticmethod
    def _top_up(
        questions: list[GeneratedQuestion], needed: int, brief: dict[str, Any]
    ) -> list[GeneratedQuestion]:
        asked = {q.text.strip().lower() for q in questions}
        filler: list[GeneratedQuestion] = []

        for unknown in brief.get("open_unknowns", []):
            if len(filler) >= needed:
                break
            text = str(unknown).strip()
            if not text or text.lower() in asked:
                continue
            # An unknown is already phrased as a thing to find out; asking it
            # directly is better than inventing a question about it.
            question = text if text.endswith("?") else f"{text}?"
            filler.append(GeneratedQuestion(text=question, workflow_target="WF1"))
            asked.add(question.strip().lower())

        wf3_fallbacks = [
            "Do you have previous ads or marketing materials we could reuse?",
            "What photography do you have of the business, products or team?",
            "Which brand assets — logo, colours, fonts — are currently in use?",
            "Which channels have you advertised on, and what worked?",
            "What does a realistic monthly marketing budget look like?",
        ]
        index = 0
        while len(filler) < needed and index < len(wf3_fallbacks):
            text = wf3_fallbacks[index]
            index += 1
            if text.strip().lower() in asked:
                continue
            filler.append(GeneratedQuestion(text=text, workflow_target="WF3"))
            asked.add(text.strip().lower())

        # Still short only if the brief was empty and the fallbacks were all
        # already asked. Repeating a question is worse than returning fewer,
        # and Django reports the real count either way.
        return filler[:needed]

    # ── Degradation ──────────────────────────────────────────────────

    @staticmethod
    def _degraded(count: int, depth: str, reason: str) -> SkillResult:
        """No questions rather than invented ones.

        C-02 degrades to a real brief because the operator's own hints are
        genuine input. There is no equivalent here: a questionnaire the model
        did not generate would be this skill's guesses presented as
        preparation, and AC-4 would store them as a DRAFT to approve.
        """
        result = GeneratedQuestionnaire(
            questions=[],
            depth=depth,
            requested_count=count,
            degraded=True,
            degraded_reason=reason,
        )
        result.recompute_coverage()
        return SkillResult(skill_id=SKILL_ID, output=result.model_dump())
