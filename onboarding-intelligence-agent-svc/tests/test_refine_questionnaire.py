"""C-04 · SKL-OIA-03, questionnaire refinement via operator instruction.

Tests cover: instruction parsing, LLM-driven refinement, count enforcement,
coverage preservation, degradation, fallback on unparseable output,
and the vocabulary boundary.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
from app.providers.llm import LLMProvider
from app.skills.models import SkillContext, SkillMeta, TenantContext
from app.skills.questionnaire_models import WORKFLOWS, GeneratedQuestionnaire
from app.skills.refine_questionnaire import RefineQuestionnaire
from tests.fakes import StubModels

VOCABULARY = ["brand_voice", "competitors", "target_audience", "business_goals"]


def llm(payload) -> LLMProvider:
    breaker = CircuitBreaker(
        BreakerConfig("llm", 5, 30, 2, 1, 60, "MANUAL_CHECKBOXES", "x")
    )
    return LLMProvider("k", breaker=breaker, client=StubModels(payload))


def meta() -> SkillMeta:
    return SkillMeta(skill_id="SKL-OIA-03", name="refine_questionnaire")


def current_questions(n: int = 6) -> list[dict]:
    return [
        {
            "text": f"Question {i}?",
            "workflow_target": ("WF1", "WF2", "WF3")[i % 3],
            "target_field": "",
        }
        for i in range(n)
    ]


def refined_payload(n: int, workflow_cycle=("WF1", "WF2", "WF3")) -> list[dict]:
    return [
        {
            "text": f"Refined question {i}?",
            "workflow_target": workflow_cycle[i % len(workflow_cycle)],
            "target_field": "",
        }
        for i in range(n)
    ]


def context(**overrides) -> SkillContext:
    input_context = {
        "instruction": "add more WF3 questions about campaign assets",
        "questions": current_questions(),
        "count": 6,
        "depth": "standard",
        "company_name": "Kalyani Roasters",
    }
    input_context.update(overrides)
    return SkillContext(
        input_prompt="refine the questionnaire",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context=input_context,
    )


async def refine(model_payload, **ctx) -> GeneratedQuestionnaire:
    skill = RefineQuestionnaire(meta(), llm=llm(model_payload), vocabulary=VOCABULARY)
    result = await skill.run(context(**ctx))
    return GeneratedQuestionnaire.model_validate(result.output)


# ── Instruction handling ────────────────────────────────────────────


@pytest.mark.unit
async def test_instruction_reaches_the_prompt():
    """The operator's instruction must appear in the LLM prompt."""
    stub = StubModels(refined_payload(6))
    skill = RefineQuestionnaire(
        meta(), llm=llm(refined_payload(6)), vocabulary=VOCABULARY
    )
    skill._llm = LLMProvider(
        "k",
        breaker=CircuitBreaker(
            BreakerConfig("llm", 5, 30, 2, 1, 60, "MANUAL_CHECKBOXES", "x")
        ),
        client=stub,
    )
    await skill.run(context(instruction="focus on WF3 campaign questions"))
    assert "focus on WF3 campaign questions" in stub.prompts[0]


@pytest.mark.unit
async def test_current_questions_reach_the_prompt():
    """The current set must be presented to the model for context."""
    stub = StubModels(refined_payload(6))
    skill = RefineQuestionnaire(
        meta(), llm=llm(refined_payload(6)), vocabulary=VOCABULARY
    )
    skill._llm = LLMProvider(
        "k",
        breaker=CircuitBreaker(
            BreakerConfig("llm", 5, 30, 2, 1, 60, "MANUAL_CHECKBOXES", "x")
        ),
        client=stub,
    )
    await skill.run(context())
    assert "Question 0?" in stub.prompts[0]


@pytest.mark.unit
async def test_no_instruction_returns_degraded():
    result = await refine(refined_payload(6), instruction="")
    assert result.degraded is True
    assert "instruction" in result.degraded_reason


@pytest.mark.unit
async def test_no_questions_returns_degraded():
    result = await refine(refined_payload(6), questions=[])
    assert result.degraded is True
    assert "questions" in result.degraded_reason


# ── Count enforcement ───────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("returned,requested", [(6, 6), (10, 6)])
async def test_count_is_honoured_exact_or_over(returned, requested):
    result = await refine(refined_payload(returned), count=requested)
    assert result.count == requested


@pytest.mark.unit
async def test_under_generation_tops_up_from_originals():
    """When the model under-generates, the original questions fill the gap."""
    result = await refine(refined_payload(3), count=6)
    assert result.count == 6
    texts = [q.text for q in result.questions]
    assert any("Question" in t for t in texts)


@pytest.mark.unit
async def test_trimming_preserves_wf3():
    """Trimming from the most-represented workflow should not remove
    the only WF3 question."""
    over = [
        {"text": f"WF1 q{i}?", "workflow_target": "WF1", "target_field": ""}
        for i in range(8)
    ] + [{"text": "Ad assets?", "workflow_target": "WF3", "target_field": ""}]

    result = await refine(over, count=3)
    assert result.count == 3
    assert "WF3" in {q.workflow_target for q in result.questions}


# ── Coverage ────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_coverage_is_reported():
    result = await refine(refined_payload(9), count=9)
    assert set(result.coverage) == set(WORKFLOWS)
    assert sum(result.coverage.values()) == pytest.approx(1.0)


@pytest.mark.unit
async def test_missing_workflow_is_named_as_thin():
    result = await refine(
        [
            {"text": f"Q{i}?", "workflow_target": "WF1", "target_field": ""}
            for i in range(6)
        ],
        count=6,
    )
    assert "WF2" in result.thin_workflows or "WF3" in result.thin_workflows


# ── Vocabulary boundary ─────────────────────────────────────────────


@pytest.mark.unit
async def test_invented_target_field_is_cleared():
    payload = [
        {"text": "A?", "workflow_target": "WF1", "target_field": "brand_voice"},
        {"text": "B?", "workflow_target": "WF2", "target_field": "fake_field"},
    ]
    result = await refine(payload, count=2)
    by_text = {q.text: q.target_field for q in result.questions}
    assert by_text["A?"] == "brand_voice"
    assert by_text["B?"] == ""


@pytest.mark.unit
async def test_vocabulary_reaches_the_prompt():
    stub = StubModels(refined_payload(6))
    skill = RefineQuestionnaire(
        meta(), llm=llm(refined_payload(6)), vocabulary=VOCABULARY
    )
    skill._llm = LLMProvider(
        "k",
        breaker=CircuitBreaker(
            BreakerConfig("llm", 5, 30, 2, 1, 60, "MANUAL_CHECKBOXES", "x")
        ),
        client=stub,
    )
    await skill.run(context())
    assert "brand_voice" in stub.prompts[0]


# ── Degradation ─────────────────────────────────────────────────────


@pytest.mark.unit
async def test_no_llm_returns_degraded():
    skill = RefineQuestionnaire(meta(), vocabulary=VOCABULARY)
    result = GeneratedQuestionnaire.model_validate((await skill.run(context())).output)
    assert result.degraded is True
    assert result.questions == []


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["not json", "{}", "[1,2,3]", '{"questions": []}'])
async def test_unparseable_output_falls_back_to_original(bad):
    """When the model returns garbage, fall back to the original questions."""
    result = await refine(bad, count=6)
    assert result.degraded is False
    assert result.count <= 6


@pytest.mark.unit
async def test_empty_completion_returns_fallback():
    """An empty string from the model should trigger fallback."""
    result = await refine("", count=6)
    assert result.degraded is True


# ── Depth ───────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_depth_reaches_the_prompt():
    stub = StubModels(refined_payload(3))
    skill = RefineQuestionnaire(
        meta(), llm=llm(refined_payload(3)), vocabulary=VOCABULARY
    )
    skill._llm = LLMProvider(
        "k",
        breaker=CircuitBreaker(
            BreakerConfig("llm", 5, 30, 2, 1, 60, "MANUAL_CHECKBOXES", "x")
        ),
        client=stub,
    )
    await skill.run(context(depth="deep", count=3))
    assert "deep" in stub.prompts[0]


@pytest.mark.unit
async def test_unknown_depth_falls_back_to_standard():
    result = await refine(refined_payload(3), count=3, depth="ultra")
    assert result.depth == "standard"


# ── Property ────────────────────────────────────────────────────────


@pytest.mark.property
@hyp_settings(max_examples=30, deadline=None)
@given(
    returned=st.integers(min_value=1, max_value=20),
    requested=st.integers(min_value=1, max_value=6),
)
async def test_count_always_honoured(returned, requested):
    """Count is met when the original set (6 questions) can top up any shortfall."""
    result = await refine(refined_payload(returned), count=requested)
    assert result.count == requested
