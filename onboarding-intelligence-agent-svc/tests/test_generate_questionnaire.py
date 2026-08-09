"""C-03 · SKL-OIA-02, count enforcement, coverage and depth.

The depth rubric lives in ``tests/fixtures/depth_rubric.json``. The card asks
for it by name: "Without it, 'deep' is untestable and will drift with every
prompt edit."

The scorer is lexical. Judging depth with a model would make this test as
unstable as the thing it measures, and a test needing a network call is one
nobody runs. It is coarse on purpose — it catches a prompt edit that quietly
turns "deep" back into a list of facts, which is the drift the card names.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.circuit_breaker.breaker import BreakerConfig, CircuitBreaker
from app.providers.llm import LLMProvider
from app.skills.generate_questionnaire import (
    DEFAULT_COUNT,
    MAX_COUNT,
    GenerateQuestionnaire,
)
from app.skills.models import SkillContext, SkillMeta, TenantContext
from app.skills.questionnaire_models import WORKFLOWS, GeneratedQuestionnaire

RUBRIC = json.loads(
    (Path(__file__).parent / "fixtures" / "depth_rubric.json").read_text()
)

VOCABULARY = ["brand_voice", "competitors", "target_audience", "business_goals"]


# ── The rubric scorer ────────────────────────────────────────────────


def _matches(question: str, markers: dict) -> bool:
    lowered = question.strip().lower()
    if any(lowered.startswith(p) for p in markers.get("prefixes", [])):
        return True
    return any(c in lowered for c in markers.get("contains", []))


def depth_profile(questions: list[str]) -> dict[str, float]:
    """Fraction of questions reading as deep, and as shallow."""
    if not questions:
        return {"deep": 0.0, "shallow": 0.0}
    deep = sum(1 for q in questions if _matches(q, RUBRIC["deep_markers"]))
    shallow = sum(1 for q in questions if _matches(q, RUBRIC["shallow_markers"]))
    return {"deep": deep / len(questions), "shallow": shallow / len(questions)}


class StubModels:
    """Stands in for ``genai.Client(...).aio.models`` (see C-02's note)."""

    def __init__(self, payload) -> None:
        self._payload = payload
        self.prompts: list[str] = []

    async def generate_content(self, *, model, contents, config=None):
        self.prompts.append(contents)
        text = (
            self._payload
            if isinstance(self._payload, str)
            else json.dumps(self._payload)
        )

        class Response:
            pass

        response = Response()
        response.text = text
        return response


def llm(payload) -> LLMProvider:
    breaker = CircuitBreaker(
        BreakerConfig("llm", 5, 30, 2, 1, 60, "MANUAL_CHECKBOXES", "x")
    )
    return LLMProvider("k", breaker=breaker, client=StubModels(payload))


def meta() -> SkillMeta:
    return SkillMeta(skill_id="SKL-OIA-02", name="generate_questionnaire")


def context(**overrides) -> SkillContext:
    input_context = {
        "count": 12,
        "depth": "standard",
        "research_brief": {
            "company_name": "Kalyani Roasters",
            "facts": [{"statement": "Founded 2016.", "source_url": "https://k/a"}],
            "open_unknowns": [f"Unknown number {i}" for i in range(8)],
        },
    }
    input_context.update(overrides)
    return SkillContext(
        input_prompt="prepare 12 questions",
        tenant_context=TenantContext(tenant_id="t-1", user_id="u-1", role="ADMIN"),
        input_context=input_context,
    )


def payload(n: int, workflow_cycle=("WF1", "WF2", "WF3")) -> list[dict]:
    return [
        {
            "text": f"Question {i}?",
            "workflow_target": workflow_cycle[i % len(workflow_cycle)],
            "target_field": "",
        }
        for i in range(n)
    ]


async def generate(model_payload, **ctx) -> GeneratedQuestionnaire:
    skill = GenerateQuestionnaire(meta(), llm=llm(model_payload), vocabulary=VOCABULARY)
    result = await skill.run(context(**ctx))
    return GeneratedQuestionnaire.model_validate(result.output)


# ── The fixture proves itself before it judges anything ──────────────


@pytest.mark.unit
def test_the_rubric_separates_its_own_exemplars():
    """A scorer that cannot tell the hand-written pairs apart is worthless as
    a judge of generated output. This runs first for that reason."""
    shallow = depth_profile(RUBRIC["exemplars"]["shallow"])
    deep = depth_profile(RUBRIC["exemplars"]["deep"])

    assert deep["deep"] >= 0.8, "the rubric missed its own deep exemplars"
    assert shallow["shallow"] >= 0.8, "the rubric missed its own shallow exemplars"
    assert deep["deep"] > shallow["deep"]


# ── AC-1 · exactly the requested count ───────────────────────────────


@pytest.mark.unit
@pytest.mark.parametrize("returned", [12, 8, 20, 1, 0])
async def test_exactly_the_requested_count_is_returned(returned):
    """AC-1 says *exactly* 12. A model asked for twelve returns eleven or
    thirteen often enough that a prompt instruction is not an implementation.
    """
    result = await generate(payload(returned), count=12)

    assert (
        result.count == 12
    ), f"model returned {returned}, skill returned {result.count}"


@pytest.mark.unit
async def test_trimming_does_not_remove_the_only_wf3_question():
    """The trap in enforcing AC-1: cutting to size must not violate AC-2.

    Ten WF1s and one WF3, trimmed to three. Dropping from the end would take
    the WF3 and leave a set FR-PREP-08 says should fail generation.
    """
    over = [
        {"text": f"WF1 question {i}?", "workflow_target": "WF1", "target_field": ""}
        for i in range(10)
    ] + [{"text": "Any old ads?", "workflow_target": "WF3", "target_field": ""}]

    result = await generate(over, count=3)

    assert result.count == 3
    assert "WF3" in {q.workflow_target for q in result.questions}


@pytest.mark.unit
async def test_topping_up_uses_the_briefs_unknowns():
    """An unknown is already a thing worth finding out. Inventing a question
    about it would be worse than asking it."""
    result = await generate(payload(2), count=6)

    assert result.count == 6
    texts = " ".join(q.text for q in result.questions)
    assert "Unknown number" in texts


@pytest.mark.unit
async def test_topping_up_adds_wf3_when_the_brief_is_empty():
    """The coverage most often short, and the one FR-PREP-08 makes fatal."""
    result = await generate(
        [{"text": "Only one?", "workflow_target": "WF1", "target_field": ""}],
        count=4,
        research_brief={"company_name": "X", "facts": [], "open_unknowns": []},
    )

    assert result.count == 4
    assert "WF3" in {q.workflow_target for q in result.questions}


@pytest.mark.unit
@pytest.mark.parametrize(
    "given,expected",
    [
        (0, 1),
        (-5, 1),
        (500, MAX_COUNT),
        ("nonsense", DEFAULT_COUNT),
        (None, DEFAULT_COUNT),
        (True, DEFAULT_COUNT),
    ],
)
async def test_an_unusable_count_is_clamped(given, expected):
    """500 questions is a wall of text and a large bill; 0 is nothing to
    approve. Both read as a client bug rather than an intention."""
    result = await generate(payload(50), count=given)

    assert result.count == expected


# ── AC-1 · depth changes the questions, not the count ────────────────


@pytest.mark.unit
async def test_depth_reaches_the_prompt():
    """FR-PREP-04: "depth changes the research budget, not the count"."""
    skill = GenerateQuestionnaire(meta(), llm=llm(payload(3)), vocabulary=VOCABULARY)
    await skill.run(context(depth="deep", count=3))

    prompt = skill._llm._client.prompts[0]
    assert "mechanism and evidence" in prompt


@pytest.mark.unit
async def test_a_deep_set_reads_as_deep_against_the_rubric():
    """AC-1's second clause, "verified against a rubric fixture"."""
    deep_payload = [
        {"text": t, "workflow_target": WORKFLOWS[i % 3], "target_field": ""}
        for i, t in enumerate(RUBRIC["exemplars"]["deep"])
    ]

    result = await generate(deep_payload, count=5, depth="deep")
    profile = depth_profile([q.text for q in result.questions])

    assert profile["deep"] >= RUBRIC["thresholds"]["deep_min_deep_fraction"]
    assert profile["shallow"] <= RUBRIC["thresholds"]["deep_max_shallow_fraction"]


@pytest.mark.unit
async def test_the_rubric_would_reject_a_shallow_deep_set():
    """The control. Without this, the assertion above would pass for a
    generator that had silently collapsed to fact questions — which is the
    exact drift the fixture exists to catch.
    """
    shallow_payload = [
        {"text": t, "workflow_target": WORKFLOWS[i % 3], "target_field": ""}
        for i, t in enumerate(RUBRIC["exemplars"]["shallow"])
    ]

    result = await generate(shallow_payload, count=5, depth="deep")
    profile = depth_profile([q.text for q in result.questions])

    assert profile["deep"] < RUBRIC["thresholds"]["deep_min_deep_fraction"]


@pytest.mark.unit
async def test_an_unknown_depth_falls_back_to_standard():
    result = await generate(payload(3), count=3, depth="extremely deep")

    assert result.depth == "standard"


# ── AC-2 · workflow tagging and the field vocabulary ─────────────────


@pytest.mark.unit
async def test_an_unlabelled_question_is_dropped_not_guessed():
    """Guessing WF1 would corrupt the coverage figure AC-3 asks the operator
    to act on."""
    result = await generate(
        [
            {"text": "Good?", "workflow_target": "WF1", "target_field": ""},
            {"text": "Unlabelled?", "workflow_target": "", "target_field": ""},
            {"text": "Bogus?", "workflow_target": "WF9", "target_field": ""},
        ],
        count=1,
    )

    assert result.count == 1
    assert result.questions[0].text == "Good?"


@pytest.mark.unit
async def test_an_invented_target_field_is_cleared():
    """Dropped here as well as at Django's boundary. Both matter: this keeps
    the coverage figure honest, Django's stops a caller that is not us."""
    result = await generate(
        [
            {"text": "A?", "workflow_target": "WF1", "target_field": "brand_voice"},
            {"text": "B?", "workflow_target": "WF2", "target_field": "vibe_score"},
        ],
        count=2,
    )

    by_text = {q.text: q.target_field for q in result.questions}
    assert by_text["A?"] == "brand_voice"
    assert by_text["B?"] == ""


@pytest.mark.unit
async def test_the_vocabulary_reaches_the_prompt():
    """A generator working blind would have most of its mappings dropped at
    the boundary — satisfying the constraint while losing J-02's joins."""
    skill = GenerateQuestionnaire(meta(), llm=llm(payload(3)), vocabulary=VOCABULARY)
    await skill.run(context(count=3))

    assert "brand_voice" in skill._llm._client.prompts[0]


@pytest.mark.unit
async def test_the_prompt_demands_wf3():
    """The card's technical note: "The skill's prompt must carry the WF3
    asset-collection intent, or the generated set silently reverts to
    brand-strategy questions only"."""
    skill = GenerateQuestionnaire(meta(), llm=llm(payload(3)), vocabulary=VOCABULARY)
    await skill.run(context(count=12))

    prompt = skill._llm._client.prompts[0]
    assert "WF3" in prompt
    assert "photography" in prompt and "ads" in prompt


# ── AC-3 · coverage is visible ───────────────────────────────────────


@pytest.mark.unit
async def test_coverage_is_three_fractions_summing_to_one():
    result = await generate(payload(9), count=9)

    assert set(result.coverage) == set(WORKFLOWS)
    assert sum(result.coverage.values()) == pytest.approx(1.0)


@pytest.mark.unit
async def test_a_missing_workflow_is_named_as_thin():
    result = await generate(payload(6, ("WF1", "WF2")), count=6)

    assert result.thin_workflows == ["WF3"]
    assert "WF3" in result.summary_line()
    assert "ask for more before approving" in result.summary_line()


@pytest.mark.unit
async def test_coverage_is_computed_after_the_count_is_enforced():
    """Trimming changes the mix. Coverage from the pre-trim set would describe
    a questionnaire the operator never sees."""
    over = [
        {"text": f"Q{i}?", "workflow_target": "WF1", "target_field": ""}
        for i in range(9)
    ] + [{"text": "Ads?", "workflow_target": "WF3", "target_field": ""}]

    result = await generate(over, count=2)

    assert sum(result.coverage.values()) == pytest.approx(1.0)
    assert result.coverage["WF1"] == pytest.approx(0.5)


# ── Degradation ──────────────────────────────────────────────────────


@pytest.mark.unit
async def test_no_llm_returns_no_questions_rather_than_invented_ones():
    """Unlike C-02, there is no honest degraded output here. A questionnaire
    the model did not generate would be this skill's guesses presented as
    preparation — and AC-4 would store them as a DRAFT to approve.
    """
    skill = GenerateQuestionnaire(meta(), vocabulary=VOCABULARY)

    result = GeneratedQuestionnaire.model_validate((await skill.run(context())).output)

    assert result.degraded is True
    assert result.questions == []
    assert "Nothing was saved" in result.summary_line()


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["not json", "{}", "[1,2,3]", '{"questions": []}'])
async def test_unusable_model_output_does_not_raise(bad):
    """Strengthened by the weak-assertion sweep.

    This asserted ``isinstance(result.count, int)``, which is true of every
    possible outcome including the skill returning nothing at all. What
    actually matters is that garbage from the model still produces the set
    the operator asked for — the top-up path is what makes that true, and the
    old assertion would have passed with it removed.
    """
    result = await generate(bad, count=5)

    assert result.count == 5, f"{bad!r} produced {result.count} questions"
    assert all(q.text.strip().endswith("?") for q in result.questions)
    assert result.degraded is False, "unusable output is not a dependency outage"


# ── Property ─────────────────────────────────────────────────────────


@pytest.mark.property
@hyp_settings(max_examples=40, deadline=None)
@given(
    returned=st.integers(min_value=0, max_value=30),
    requested=st.integers(min_value=1, max_value=25),
)
async def test_the_count_is_always_honoured(returned, requested):
    """AC-1 over arbitrary model behaviour.

    The interesting half is under-generation: topping up must reach the number
    without repeating a question, or the operator approves a set with
    duplicates in it.
    """
    result = await generate(payload(returned), count=requested)

    # The previous version of this assertion was
    #     result.count == requested or result.count < requested
    # which is `count <= requested` — it accepted every short result and so
    # asserted nothing about the property it was named for. Review caught the
    # shortfall it was hiding.
    #
    # The fixture brief carries 8 unknowns and the standing pool holds 15, so
    # any request up to 23 is reachable and must be met exactly.
    assert result.count == requested, f"asked for {requested}, got {result.count}"

    texts = [q.text.strip().lower() for q in result.questions]
    assert len(texts) == len(set(texts)), "a question was duplicated"


# ── Review finding · the count must be met, or reported ──────────────


@pytest.mark.unit
async def test_a_large_request_is_still_met_exactly():
    """The gap review found: topping up drew only on the brief's unknowns and
    five WF3 fallbacks, so a big request with a thin brief came back short
    while claiming to honour the count."""
    result = await generate(payload(2), count=20)

    assert result.count == 20
    texts = [q.text.strip().lower() for q in result.questions]
    assert len(texts) == len(set(texts))


@pytest.mark.unit
async def test_top_up_questions_are_real_questions():
    """Not numbered filler. An operator approving a questionnaire should not
    be able to tell which questions came from the standing pool — padding to
    hit a number with "Additional question 13" would satisfy AC-1 while
    handing them something that is not a question.
    """
    result = await generate(payload(1), count=12)

    for question in result.questions:
        assert question.text.strip().endswith("?"), question.text
        assert "question 1" not in question.text.lower()


@pytest.mark.unit
async def test_an_unmeetable_request_reports_the_shortfall(caplog):
    """Beyond the reachable pool the set is short — and says so, rather than
    letting the operator assume this is what they asked for."""
    result = await generate(
        payload(0),
        count=MAX_COUNT,
        research_brief={"company_name": "X", "facts": [], "open_unknowns": []},
    )

    assert result.count < MAX_COUNT
    assert str(result.requested_count) in result.summary_line()
    assert "requested" in result.summary_line()


@pytest.mark.unit
async def test_the_standing_pool_leads_with_wf3():
    """The coverage most often short, and the one FR-PREP-08 makes fatal."""
    from app.skills.generate_questionnaire import STANDING_QUESTIONS

    assert STANDING_QUESTIONS[0][1] == "WF3"
    assert sum(1 for _, w in STANDING_QUESTIONS if w == "WF3") >= 5


@pytest.mark.unit
def test_the_standing_pool_has_no_duplicates():
    """A duplicate would silently reduce the reachable count."""
    from app.skills.generate_questionnaire import STANDING_QUESTIONS

    texts = [t.strip().lower() for t, _ in STANDING_QUESTIONS]
    assert len(texts) == len(set(texts))


@pytest.mark.unit
async def test_an_empty_completion_degrades_rather_than_topping_up():
    """The distinction the sweep surfaced.

    An empty completion is a *provider* failure — LLMProvider treats it as one
    deliberately, so a safety block cannot silently produce nothing — and it
    reaches this skill as LLMUnavailable. Output that is present but
    unparseable is a different thing: the model answered, we could not use it,
    and the top-up path fills the set.

    The old test parametrised both together behind
    ``assert isinstance(result.count, int)``, which was true either way and
    hid that they take different paths.
    """
    result = await generate("", count=5)

    assert result.degraded is True
    assert result.questions == []
    assert "Nothing was saved" in result.summary_line()
