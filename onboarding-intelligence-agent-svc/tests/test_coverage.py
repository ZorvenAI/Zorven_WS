"""G-06 — WF1/WF2/WF3 coverage computation.

Unit tests for the pure coverage function, property tests for invariants,
and a skill-level test for SKL-OIA-09's output shape.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.coverage import compute_coverage

pytestmark = pytest.mark.unit


# ── Helpers ───────────────────────────────────────────────────────────


def _q(
    text: str,
    wf: str = "WF1",
    status: str = "OPEN",
    target_field: str = "unknown",
    origin: str = "PREPARED",
) -> dict:
    return {
        "id": text.lower().replace(" ", "_"),
        "text": text,
        "workflow_target": wf,
        "status": status,
        "target_field": target_field,
        "origin": origin,
    }


# ── Basic coverage computation ────────────────────────────────────────


def test_all_green_full_coverage():
    questions = [
        _q("Company name?", wf="WF1", status="GREEN"),
        _q("Brand voice?", wf="WF2", status="GREEN"),
        _q("Ad budget?", wf="WF3", status="GREEN"),
    ]
    result = compute_coverage(questions)
    assert result.wf1.pct == 1.0
    assert result.wf2.pct == 1.0
    assert result.wf3.pct == 1.0


def test_none_green_zero_coverage():
    questions = [
        _q("Company name?", wf="WF1"),
        _q("Brand voice?", wf="WF2"),
        _q("Ad budget?", wf="WF3"),
    ]
    result = compute_coverage(questions)
    assert result.wf1.pct == 0.0
    assert result.wf2.pct == 0.0
    assert result.wf3.pct == 0.0


def test_mixed_coverage():
    questions = [
        _q("Company name?", wf="WF1", status="GREEN"),
        _q("Founded year?", wf="WF1"),
        _q("Industry?", wf="WF1", status="GREEN"),
    ]
    result = compute_coverage(questions)
    assert abs(result.wf1.pct - 2.0 / 3.0) < 1e-9


def test_per_workflow_independence():
    """WF1 at 100%, WF3 at 0% — computed independently."""
    questions = [
        _q("Company name?", wf="WF1", status="GREEN"),
        _q("Brand voice?", wf="WF2", status="GREEN"),
        _q("Ad budget?", wf="WF3"),
        _q("Sales channels?", wf="WF3"),
    ]
    result = compute_coverage(questions)
    assert result.wf1.pct == 1.0
    assert result.wf2.pct == 1.0
    assert result.wf3.pct == 0.0


def test_empty_questions_zero_coverage():
    result = compute_coverage([])
    assert result.wf1.pct == 0.0
    assert result.wf2.pct == 0.0
    assert result.wf3.pct == 0.0


def test_adhoc_questions_count():
    """ADHOC origin questions count the same as PREPARED."""
    questions = [
        _q("Company name?", wf="WF1", status="GREEN", origin="PREPARED"),
        _q("Retail locations?", wf="WF3", status="GREEN", origin="ADHOC"),
    ]
    result = compute_coverage(questions)
    assert result.wf1.pct == 1.0
    assert result.wf3.pct == 1.0


# ── Covered and missing lists ────────────────────────────────────────


def test_covered_lists_green_questions():
    questions = [
        _q("Company name?", wf="WF1", status="GREEN"),
        _q("Founded year?", wf="WF1"),
    ]
    result = compute_coverage(questions)
    assert "Company name?" in result.wf1.covered
    assert "Founded year?" in result.wf1.missing


def test_missing_fields_tracked():
    questions = [
        _q("Ad budget?", wf="WF3", target_field="marketing_budget_range"),
    ]
    result = compute_coverage(questions)
    assert "marketing_budget_range" in result.wf3.missing_fields


# ── Satisfied and blocking_gaps ───────────────────────────────────────


def test_satisfied_when_all_above_threshold():
    questions = [
        _q("Q1", wf="WF1", status="GREEN"),
        _q("Q2", wf="WF2", status="GREEN"),
        _q("Q3", wf="WF3", status="GREEN"),
    ]
    result = compute_coverage(questions, threshold=0.7)
    assert result.satisfied is True


def test_not_satisfied_when_one_below():
    questions = [
        _q("Q1", wf="WF1", status="GREEN"),
        _q("Q2", wf="WF2", status="GREEN"),
        _q("Q3", wf="WF3"),
    ]
    result = compute_coverage(questions, threshold=0.7)
    assert result.satisfied is False


def test_not_satisfied_when_empty():
    """No questions at all means no coverage — not satisfied."""
    result = compute_coverage([])
    assert result.satisfied is False


def test_blocking_gaps_lists_missing():
    questions = [
        _q("Q1", wf="WF1", status="GREEN"),
        _q("Q2", wf="WF2", status="GREEN"),
        _q("Ad budget?", wf="WF3", target_field="marketing_budget_range"),
        _q("Sales channels?", wf="WF3", target_field="sales_channels"),
    ]
    result = compute_coverage(questions, threshold=0.7)
    assert len(result.blocking_gaps) == 2
    texts = [g["question_text"] for g in result.blocking_gaps]
    assert "Ad budget?" in texts
    assert "Sales channels?" in texts
    assert all(g["workflow"] == "WF3" for g in result.blocking_gaps)


def test_blocking_gaps_empty_when_satisfied():
    questions = [
        _q("Q1", wf="WF1", status="GREEN"),
        _q("Q2", wf="WF2", status="GREEN"),
        _q("Q3", wf="WF3", status="GREEN"),
    ]
    result = compute_coverage(questions, threshold=0.5)
    assert result.blocking_gaps == []


def test_coverage_threshold_configurable():
    questions = [
        _q("Q1", wf="WF1", status="GREEN"),
        _q("Q2", wf="WF1"),
        _q("Q3", wf="WF2", status="GREEN"),
        _q("Q4", wf="WF3", status="GREEN"),
    ]
    assert compute_coverage(questions, threshold=0.5).satisfied is True
    assert compute_coverage(questions, threshold=0.6).satisfied is False


# ── AC-2 named test: WF3 low without assets ──────────────────────────


def test_wf3_low_without_assets():
    """AC-2: WF1 high, WF3 low → specific missing items are nameable."""
    questions = [
        _q("Company name?", wf="WF1", status="GREEN"),
        _q("Founded year?", wf="WF1", status="GREEN"),
        _q("Mission?", wf="WF1", status="GREEN"),
        _q("Brand voice?", wf="WF2", status="GREEN"),
        _q("Competitors?", wf="WF2", status="GREEN"),
        _q("Business photos?", wf="WF3", target_field="business_photos"),
        _q("Previous ads?", wf="WF3", target_field="previous_ads"),
    ]
    result = compute_coverage(questions, threshold=0.5)
    assert result.wf1.pct == 1.0
    assert result.wf3.pct == 0.0
    assert not result.satisfied
    gap_texts = [g["question_text"] for g in result.blocking_gaps]
    assert "Business photos?" in gap_texts
    assert "Previous ads?" in gap_texts


# ── as_map helper ─────────────────────────────────────────────────────


def test_as_map_returns_three_fractions():
    result = compute_coverage([_q("Q1", wf="WF1", status="GREEN")])
    m = result.as_map()
    assert set(m.keys()) == {"WF1", "WF2", "WF3"}
    assert m["WF1"] == 1.0
    assert m["WF2"] == 0.0
    assert m["WF3"] == 0.0


def test_by_workflow_accessor():
    result = compute_coverage([_q("Q1", wf="WF2", status="GREEN")])
    wf2 = result.by_workflow("WF2")
    assert wf2.pct == 1.0


# ── SKL-OIA-09 skill body ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skill_returns_correct_output():
    """SKL-OIA-09 run() produces the expected SkillResult shape."""
    from app.skills.check_workflow_coverage import CheckWorkflowCoverage
    from app.skills.models import SkillContext, SkillMeta, TenantContext

    skill = CheckWorkflowCoverage(
        meta=SkillMeta(skill_id="SKL-OIA-09", name="check_workflow_coverage")
    )
    ctx = SkillContext(
        input_prompt="assess coverage",
        tenant_context=TenantContext(tenant_id="t-1"),
        input_context={
            "question_states": [
                _q("Company name?", wf="WF1", status="GREEN"),
                _q("Ad budget?", wf="WF3"),
            ]
        },
        config={"coverage_threshold": 0.7},
    )
    result = await skill.run(ctx)
    assert result.skill_id == "SKL-OIA-09"
    assert "coverage" in result.output
    assert "satisfied" in result.output
    assert "blocking_gaps" in result.output
    coverage = result.output["coverage"]
    assert set(coverage.keys()) == {"WF1", "WF2", "WF3"}
    assert coverage["WF1"]["pct"] == 1.0
    assert coverage["WF3"]["pct"] == 0.0
    assert len(coverage["WF3"]["missing"]) == 1


# ── Property tests ────────────────────────────────────────────────────


WORKFLOW_ST = st.sampled_from(["WF1", "WF2", "WF3"])
STATUS_ST = st.sampled_from(["OPEN", "GREEN"])

QUESTION_ST = st.fixed_dictionaries(
    {
        "text": st.text(min_size=1, max_size=30),
        "workflow_target": WORKFLOW_ST,
        "status": STATUS_ST,
        "target_field": st.text(min_size=1, max_size=20),
        "origin": st.sampled_from(["PREPARED", "ADHOC"]),
    }
)


@settings(max_examples=50, deadline=None)
@given(questions=st.lists(QUESTION_ST, max_size=30))
def test_fractions_always_between_zero_and_one(questions):
    result = compute_coverage(questions)
    for wf in ["WF1", "WF2", "WF3"]:
        pct = result.by_workflow(wf).pct
        assert 0.0 <= pct <= 1.0, f"{wf} pct out of range: {pct}"


@settings(max_examples=50, deadline=None)
@given(questions=st.lists(QUESTION_ST, max_size=30))
def test_three_fractions_never_blended(questions):
    """FR-LIVE-09: always three separate values in as_map()."""
    m = compute_coverage(questions).as_map()
    assert set(m.keys()) == {"WF1", "WF2", "WF3"}


@settings(max_examples=50, deadline=None)
@given(questions=st.lists(QUESTION_ST, max_size=30))
def test_covered_plus_missing_equals_total(questions):
    result = compute_coverage(questions)
    for wf in ["WF1", "WF2", "WF3"]:
        wc = result.by_workflow(wf)
        total_input = len([q for q in questions if q.get("workflow_target") == wf])
        assert len(wc.covered) + len(wc.missing) == total_input
