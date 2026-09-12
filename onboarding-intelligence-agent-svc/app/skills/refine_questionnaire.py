"""SKL-OIA-03 — Refine a questionnaire to the operator's instruction.

Design §8.1 · implemented by story C-04.

The operator has a DRAFT questionnaire from SKL-OIA-02 and sends a natural
language edit instruction — "add more WF3 questions", "remove question 5",
"make them deeper", "focus on brand story". This skill interprets the
instruction via Gemini and produces a revised set of questions that honours
coverage and count constraints.

The refined set is stored as a new DRAFT via ``BackendClient.store_questionnaire``.
The operator can then review, further refine, or approve it through
the QuestionnaireViewSet's individual mutation actions (rewrite, drop,
reorder) or via another call to this skill.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.providers.llm import LLMProvider, LLMUnavailable
from app.services.backend_client import BackendClient
from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillResult
from app.skills.questionnaire_models import (
    WORKFLOWS,
    GeneratedQuestion,
    GeneratedQuestionnaire,
)

logger = get_logger(__name__)

SKILL_ID = "SKL-OIA-03"

PROMPT = """\
You are refining a questionnaire for a brand onboarding meeting.

CURRENT QUESTIONS:
{current_questions}

OPERATOR INSTRUCTION:
{instruction}

Business: {company_name}
Desired depth: {depth}
Desired count: {count}

Apply the operator's instruction to the current set. Rules:
1. Keep every question the instruction does not ask to change.
2. Where the instruction asks to add, remove, reword, reorder, or change
   focus, do so. Preserve the workflow_target and target_field of unchanged
   questions.
3. The final set must have exactly {count} questions (add or trim to hit it).
4. Every question must carry:
   "text": the question, addressed to the business owner.
   "workflow_target": exactly one of "WF1", "WF2", "WF3".
   "target_field": one of the allowed field names below, or "" if none apply.
5. You MUST include at least {wf3_min} WF3 questions.

Allowed target_field values:
{vocabulary}

Return ONLY a JSON array of question objects. No prose, no code fence.
"""


class RefineQuestionnaire(BaseSkill):
    """Refine a questionnaire to the operator's instruction."""

    def __init__(
        self,
        meta: Any,
        *,
        llm: LLMProvider | None = None,
        backend: BackendClient | None = None,
        vocabulary: list[str] | None = None,
    ) -> None:
        super().__init__(meta)
        self._llm = llm
        self._backend = backend
        self._vocabulary = vocabulary or []

    def set_vocabulary(self, fields: list[str]) -> None:
        self._vocabulary = sorted(set(fields))

    async def run(self, context: SkillContext) -> SkillResult:
        hints = context.input_context or {}
        instruction = str(hints.get("instruction") or "").strip()
        current_questions = hints.get("questions") or []
        count = self._requested_count(hints, len(current_questions))
        depth = self._requested_depth(hints)
        company_name = hints.get("company_name") or "(unnamed)"

        if not instruction:
            return self._error_result("no refinement instruction provided")

        if not current_questions:
            return self._error_result("no current questions to refine")

        if self._llm is None:
            return self._degraded(count, depth, "no LLM is configured")

        try:
            raw = await self._llm.generate(
                self._prompt(
                    current_questions, instruction, company_name, count, depth
                ),
                temperature=0.3,
            )
        except LLMUnavailable as exc:
            logger.warning("refine_questionnaire_degraded", reason=exc.reason)
            return self._degraded(count, depth, exc.reason)

        questions = self._parse(raw)
        if not questions:
            logger.warning("refine_questionnaire_parse_failed")
            return self._fallback(current_questions, count, depth)

        questions = self._enforce_count(questions, count, current_questions)

        result = GeneratedQuestionnaire(
            questions=questions,
            depth=depth,
            requested_count=count,
        )
        result.recompute_coverage()

        if self._backend is not None:
            session_id = hints.get("session_id")
            company_id = hints.get("company_id")
            chat_session_id = hints.get("chat_session_id")
            await self._backend.store_questionnaire(
                tenant_id=context.tenant_context.tenant_id,
                questions=[q.model_dump() for q in result.questions],
                depth=result.depth,
                session_id=session_id,
                company_id=company_id,
                chat_session_id=chat_session_id,
            )

        return SkillResult(skill_id=SKILL_ID, output=result.model_dump())

    # ── Prompt building ────────���───────────────────────────────────

    def _prompt(
        self,
        current_questions: list[dict[str, Any]],
        instruction: str,
        company_name: str,
        count: int,
        depth: str,
    ) -> str:
        formatted = json.dumps(current_questions, indent=2)
        return PROMPT.format(
            current_questions=formatted,
            instruction=instruction,
            company_name=company_name,
            depth=depth,
            count=count,
            wf3_min=max(2, count // 5),
            vocabulary="\n".join(f"  {f}" for f in self._vocabulary)
            or '  (none available — use "" for every target_field)',
        )

    # ── Parsing ────────────────────────────────────────────────────

    def _parse(self, raw: str) -> list[GeneratedQuestion]:
        text = raw.strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError:
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
                        target_field=field if (not allowed or field in allowed) else "",
                    )
                )
            except ValueError:
                continue
        return questions

    # ── Count enforcement ──────────────────────────────────────────

    @staticmethod
    def _enforce_count(
        questions: list[GeneratedQuestion],
        count: int,
        originals: list[dict[str, Any]] | None = None,
    ) -> list[GeneratedQuestion]:
        if len(questions) > count:
            return RefineQuestionnaire._trim(questions, count)
        if len(questions) < count:
            return questions + RefineQuestionnaire._top_up(
                questions, count - len(questions), originals or []
            )
        return questions

    @staticmethod
    def _top_up(
        questions: list[GeneratedQuestion],
        needed: int,
        originals: list[dict[str, Any]],
    ) -> list[GeneratedQuestion]:
        """Fill from the original set when the model under-generates."""
        asked = {q.text.strip().lower() for q in questions}
        filler: list[GeneratedQuestion] = []
        for item in originals:
            if len(filler) >= needed:
                break
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text or text.lower() in asked:
                continue
            wf = str(item.get("workflow_target") or "WF1").strip().upper()
            if wf not in WORKFLOWS:
                wf = "WF1"
            filler.append(
                GeneratedQuestion(
                    text=text,
                    workflow_target=wf,
                    target_field=str(item.get("target_field") or ""),
                )
            )
            asked.add(text.lower())
        return filler[:needed]

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
            for index in range(len(kept) - 1, -1, -1):
                if kept[index].workflow_target == fattest:
                    kept.pop(index)
                    break
            else:
                kept.pop()
        return kept

    # ── Request helpers ────────────────────────────────────────────

    @staticmethod
    def _requested_count(hints: dict[str, Any], fallback: int) -> int:
        raw = hints.get("count")
        if raw is None:
            return max(1, fallback) if fallback else 10
        try:
            count = int(raw)
        except (TypeError, ValueError):
            return max(1, fallback) if fallback else 10
        if isinstance(raw, bool):
            return max(1, fallback) if fallback else 10
        return max(1, min(count, 40))

    @staticmethod
    def _requested_depth(hints: dict[str, Any]) -> str:
        depth = str(hints.get("depth") or "standard").strip().lower()
        return depth if depth in ("quick", "standard", "deep") else "standard"

    # ── Fallback and degradation ────────────────���──────────────────

    @staticmethod
    def _fallback(
        current_questions: list[dict[str, Any]], count: int, depth: str
    ) -> SkillResult:
        """When the LLM returns unparseable output, return the original set."""
        questions: list[GeneratedQuestion] = []
        for item in current_questions:
            if not isinstance(item, dict):
                continue
            try:
                questions.append(
                    GeneratedQuestion(
                        text=str(item.get("text") or "").strip(),
                        workflow_target=str(item.get("workflow_target") or "WF1"),
                        target_field=str(item.get("target_field") or ""),
                    )
                )
            except ValueError:
                continue

        result = GeneratedQuestionnaire(
            questions=questions[:count] if questions else [],
            depth=depth,
            requested_count=count,
        )
        result.recompute_coverage()
        return SkillResult(skill_id=SKILL_ID, output=result.model_dump())

    @staticmethod
    def _degraded(count: int, depth: str, reason: str) -> SkillResult:
        result = GeneratedQuestionnaire(
            questions=[],
            depth=depth,
            requested_count=count,
            degraded=True,
            degraded_reason=reason,
        )
        result.recompute_coverage()
        return SkillResult(skill_id=SKILL_ID, output=result.model_dump())

    @staticmethod
    def _error_result(reason: str) -> SkillResult:
        result = GeneratedQuestionnaire(
            questions=[],
            degraded=True,
            degraded_reason=reason,
        )
        result.recompute_coverage()
        return SkillResult(skill_id=SKILL_ID, output=result.model_dump())
