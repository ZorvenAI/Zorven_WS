"""G-03 · SKL-OIA-05, answer sufficiency scoring.

No mocks. The skill is driven through a real LLMProvider with a local stand-in
for the model, same pattern as test_research_business.py. The provider's
breaker, error handling and text extraction all still run.
"""

from __future__ import annotations

import json

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
from app.logic.green_signal_integrity import og06_green_signal_integrity
from app.logic.guardrails import Action
from app.providers.llm import LLMProvider
from app.skills.evaluate_answer_sufficiency import EvaluateAnswerSufficiency
from app.skills.models import SkillContext, SkillMeta, TenantContext


def meta() -> SkillMeta:
    return SkillMeta(
        skill_id="SKL-OIA-05",
        name="evaluate_answer_sufficiency",
        description="sufficiency scoring",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
    )


def context(question="When was the company founded?", **overrides) -> SkillContext:
    input_context = {
        "question": question,
        "attached_spans": [
            {
                "recording_id": "r-1",
                "t_start": 10.0,
                "t_end": 15.0,
                "text": "We were founded in 2016 by two coffee roasters.",
            }
        ],
        "target_field": "founded_year",
    }
    input_context.update(overrides.pop("input_context", {}))
    return SkillContext(
        input_prompt="Score answer sufficiency",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context=input_context,
        config=overrides.pop("config", {"sufficiency_green_threshold": 0.7}),
        **overrides,
    )


def brk(name: str = "llm") -> CircuitBreaker:
    return CircuitBreaker(
        BreakerConfig(
            name=name,
            failure_threshold=3,
            window_seconds=60,
            success_threshold=1,
            half_open_max_calls=1,
            reset_timeout_seconds=60,
            degraded_mode="MANUAL_CHECKBOXES",
            user_message="unavailable",
        )
    )


class StubModels:
    """Stand-in for ``genai.Client(...).aio.models``."""

    def __init__(self, text: str = "", raises: Exception | None = None) -> None:
        self._text = text
        self._raises = raises
        self.prompts: list[str] = []

    async def generate_content(self, *, model, contents, config=None):
        self.prompts.append(contents)
        if self._raises:
            raise self._raises

        class Response:
            text = self._text

        return Response()


def llm_for(model: StubModels) -> LLMProvider:
    return LLMProvider("k", breaker=brk(), client=model)


async def _collect(skill, ctx):
    chunks = []
    async for chunk in skill.stream(ctx):
        chunks.append(chunk)
    return chunks


# ── Happy path: well-answered question ──────────────────────────────


async def test_skill_scores_answered_question():
    """SKL-OIA-05 returns score >= 0.7 for a well-answered question."""
    model = StubModels(text=json.dumps({"score": 0.88, "missing_aspects": []}))
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())
    assert len(chunks) == 1

    result = chunks[0]
    assert result["type"] == "sufficiency_result"
    assert result["sufficiency_score"] == 0.88
    assert result["green"] is True
    assert result["missing_aspects"] == []
    assert len(result["evidence"]) == 1


async def test_skill_scores_unanswered_question():
    """SKL-OIA-05 returns score < 0.7 for an unanswered question."""
    model = StubModels(
        text=json.dumps(
            {
                "score": 0.3,
                "missing_aspects": ["founding year not mentioned"],
            }
        )
    )
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())
    result = chunks[0]

    assert result["sufficiency_score"] == 0.3
    assert result["green"] is False
    assert "founding year not mentioned" in result["missing_aspects"]


async def test_skill_returns_missing_aspects():
    """missing_aspects is populated when score < 0.7."""
    model = StubModels(
        text=json.dumps(
            {
                "score": 0.5,
                "missing_aspects": ["company name", "location"],
            }
        )
    )
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())
    result = chunks[0]

    assert len(result["missing_aspects"]) == 2
    assert "company name" in result["missing_aspects"]
    assert "location" in result["missing_aspects"]


async def test_skill_evidence_shape():
    """Evidence spans match {recording_id, t_start, t_end}."""
    model = StubModels(text=json.dumps({"score": 0.9, "missing_aspects": []}))
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    ctx = context(
        input_context={
            "question": "Brand values?",
            "attached_spans": [
                {"recording_id": "r-1", "t_start": 10.0, "t_end": 15.0, "text": "a"},
                {"recording_id": "r-1", "t_start": 20.0, "t_end": 25.0, "text": "b"},
            ],
            "target_field": "values",
        }
    )
    chunks = await _collect(skill, ctx)
    evidence = chunks[0]["evidence"]

    assert len(evidence) == 2
    for span in evidence:
        assert "recording_id" in span
        assert "t_start" in span
        assert "t_end" in span


# ── Edge cases ──────────────────────────────────────────────────────


async def test_no_spans_returns_zero():
    """Empty evidence list returns score 0.0 without calling LLM."""
    model = StubModels()
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    ctx = context(
        input_context={
            "question": "Test?",
            "attached_spans": [],
            "target_field": "test",
        }
    )
    chunks = await _collect(skill, ctx)

    assert chunks[0]["sufficiency_score"] == 0.0
    assert chunks[0]["green"] is False
    assert model.prompts == [], "LLM should not have been called"


async def test_bad_json_from_llm_returns_zero():
    """Unparseable LLM response degrades to score 0.0."""
    model = StubModels(text="this is not valid JSON at all")
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())
    assert chunks[0]["sufficiency_score"] == 0.0
    assert chunks[0]["green"] is False


async def test_score_clamped_to_0_1():
    """Scores outside [0, 1] are clamped."""
    model = StubModels(text=json.dumps({"score": 1.5, "missing_aspects": []}))
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())
    assert chunks[0]["sufficiency_score"] == 1.0


async def test_markdown_fenced_json():
    """LLM response wrapped in ```json fences is still parsed."""
    model = StubModels(text='```json\n{"score": 0.75, "missing_aspects": []}\n```')
    skill = EvaluateAnswerSufficiency(meta(), llm=llm_for(model))

    chunks = await _collect(skill, context())
    assert chunks[0]["sufficiency_score"] == 0.75
    assert chunks[0]["green"] is True


# ── OG-06 guardrail ────────────────────────────────────────────────


def _suf_context():
    return SkillContext(
        input_prompt="score",
        tenant_context=TenantContext(tenant_id="t-1", role="ADMIN"),
    )


def test_og06_passes_non_green():
    """OG-06 passes through non-green results."""
    payload = {"green": False, "sufficiency_score": 0.3, "evidence": []}
    verdict = og06_green_signal_integrity(payload, _suf_context())
    assert verdict.action is Action.PASS


def test_og06_passes_green_with_evidence():
    """OG-06 passes green results that have evidence."""
    payload = {
        "green": True,
        "sufficiency_score": 0.9,
        "evidence": [{"recording_id": "r-1", "t_start": 1.0, "t_end": 2.0}],
    }
    verdict = og06_green_signal_integrity(payload, _suf_context())
    assert verdict.action is Action.PASS


def test_og06_blocks_green_without_evidence():
    """OG-06 blocks a green signal that has no evidence spans."""
    payload = {"green": True, "sufficiency_score": 0.95, "evidence": []}
    verdict = og06_green_signal_integrity(payload, _suf_context())
    assert verdict.action is Action.BLOCK
    assert "evidence" in verdict.detail.lower()


def test_og06_passes_non_dict():
    """OG-06 passes through non-dict payloads without crashing."""
    verdict = og06_green_signal_integrity("just a string", _suf_context())
    assert verdict.action is Action.PASS
