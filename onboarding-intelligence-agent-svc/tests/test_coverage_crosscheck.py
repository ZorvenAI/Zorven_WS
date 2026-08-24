"""J-02 — Coverage cross-validation tests.

No mocks: pure logic, no I/O dependencies.
"""

import pytest

from app.logic.coverage import CoverageResult, WorkflowCoverage, compute_coverage
from app.logic.coverage_crosscheck import crosscheck_coverage

pytestmark = pytest.mark.unit


def _make_coverage(wf1: float, wf2: float, wf3: float) -> CoverageResult:
    return CoverageResult(
        wf1=WorkflowCoverage(pct=wf1),
        wf2=WorkflowCoverage(pct=wf2),
        wf3=WorkflowCoverage(pct=wf3),
        satisfied=all(p >= 0.7 for p in (wf1, wf2, wf3)),
    )


def test_identical_coverage_no_differences():
    """Full and incremental agree — empty difference list."""
    full = _make_coverage(0.8, 0.9, 0.7)
    incremental = {"WF1": "0.8", "WF2": "0.9", "WF3": "0.7"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert diffs == []


def test_material_difference_logged():
    """A 10-percentage-point difference produces an entry with cause."""
    full = _make_coverage(0.8, 0.6, 0.7)
    incremental = {"WF1": "0.8", "WF2": "0.5", "WF3": "0.7"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert len(diffs) == 1
    assert diffs[0].workflow == "WF2"
    assert diffs[0].delta == pytest.approx(0.1, abs=0.01)
    assert diffs[0].cause


def test_tolerance_respected():
    """A 3-point difference (below 5-point tolerance) produces no entry."""
    full = _make_coverage(0.8, 0.73, 0.7)
    incremental = {"WF1": "0.8", "WF2": "0.7", "WF3": "0.7"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert diffs == []


def test_no_incremental_returns_empty():
    """When no incremental data exists, crosscheck is skipped."""
    full = _make_coverage(0.8, 0.9, 0.7)
    diffs = crosscheck_coverage(full, None, tolerance=0.05)
    assert diffs == []


def test_multiple_workflows_differ():
    """All three workflows can diverge independently."""
    full = _make_coverage(0.9, 0.3, 0.1)
    incremental = {"WF1": "0.5", "WF2": "0.8", "WF3": "0.7"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert len(diffs) == 3
    workflows = {d.workflow for d in diffs}
    assert workflows == {"WF1", "WF2", "WF3"}


def test_incremental_higher_cause():
    """When incremental is higher, cause message reflects that."""
    full = _make_coverage(0.5, 0.9, 0.7)
    incremental = {"WF1": "0.8", "WF2": "0.9", "WF3": "0.7"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert len(diffs) == 1
    assert "higher coverage" in diffs[0].cause


def test_full_higher_cause():
    """When full is higher, cause message reflects that."""
    full = _make_coverage(0.9, 0.9, 0.7)
    incremental = {"WF1": "0.5", "WF2": "0.9", "WF3": "0.7"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert len(diffs) == 1
    assert "more answered" in diffs[0].cause


def test_crosscheck_with_real_compute_coverage():
    """End-to-end: compute_coverage then crosscheck."""
    questions = [
        {
            "text": "Q1",
            "workflow_target": "WF1",
            "status": "GREEN",
            "target_field": "name",
        },
        {
            "text": "Q2",
            "workflow_target": "WF1",
            "status": "OPEN",
            "target_field": "mission",
        },
        {
            "text": "Q3",
            "workflow_target": "WF2",
            "status": "GREEN",
            "target_field": "market",
        },
        {
            "text": "Q4",
            "workflow_target": "WF3",
            "status": "GREEN",
            "target_field": "channel",
        },
    ]

    full = compute_coverage(questions)
    incremental = {"WF1": "0.5", "WF2": "1.0", "WF3": "1.0"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert diffs == []


def test_crosscheck_missing_workflow_key():
    """A missing workflow key in incremental is treated as 0.0."""
    full = _make_coverage(0.8, 0.9, 0.7)
    incremental = {"WF1": "0.8"}

    diffs = crosscheck_coverage(full, incremental, tolerance=0.05)
    assert len(diffs) == 2
    workflows = {d.workflow for d in diffs}
    assert "WF2" in workflows
    assert "WF3" in workflows
