"""G-06 — WF1/WF2/WF3 coverage computation.

Pure arithmetic on question state: group by workflow_target, count GREEN vs
total, compute fractions. No LLM, no Redis, no I/O — a function that takes
a list of question dicts and returns a result.

Shared by the LIVE path (ws.py calls it directly after sufficiency) and the
PROCESS path (SKL-OIA-09 calls it through the skill registry in J-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

WORKFLOWS = ("WF1", "WF2", "WF3")


@dataclass
class WorkflowCoverage:
    """Per-workflow breakdown: which questions are covered, which are not."""

    covered: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    pct: float = 0.0


@dataclass
class CoverageResult:
    """Coverage across all three workflows."""

    wf1: WorkflowCoverage = field(default_factory=WorkflowCoverage)
    wf2: WorkflowCoverage = field(default_factory=WorkflowCoverage)
    wf3: WorkflowCoverage = field(default_factory=WorkflowCoverage)
    satisfied: bool = False
    blocking_gaps: list[dict[str, str]] = field(default_factory=list)

    def as_map(self) -> dict[str, float]:
        return {"WF1": self.wf1.pct, "WF2": self.wf2.pct, "WF3": self.wf3.pct}

    def by_workflow(self, wf: str) -> WorkflowCoverage:
        return {"WF1": self.wf1, "WF2": self.wf2, "WF3": self.wf3}[wf]


def compute_coverage(
    questions: list[dict[str, Any]],
    threshold: float = 0.7,
) -> CoverageResult:
    """Group questions by workflow_target, compute per-WF coverage fractions.

    Each question dict must have at least ``workflow_target``, ``status``,
    ``text``, and ``target_field``. These are the fields that
    ``LiveSessionManager.get_questions()`` and ``set_questions()`` guarantee.
    """
    buckets: dict[str, list[dict[str, Any]]] = {wf: [] for wf in WORKFLOWS}

    for q in questions:
        wf = q.get("workflow_target", "WF1")
        if wf in buckets:
            buckets[wf].append(q)

    wf_coverages: dict[str, WorkflowCoverage] = {}
    for wf in WORKFLOWS:
        qs = buckets[wf]
        covered = [q.get("text", "") for q in qs if q.get("status") == "GREEN"]
        missing = [q.get("text", "") for q in qs if q.get("status") != "GREEN"]
        missing_fields = [
            q.get("target_field", "") for q in qs if q.get("status") != "GREEN"
        ]
        total = len(covered) + len(missing)
        pct = len(covered) / total if total > 0 else 0.0
        wf_coverages[wf] = WorkflowCoverage(
            covered=covered,
            missing=missing,
            missing_fields=missing_fields,
            pct=pct,
        )

    satisfied = all(wf_coverages[wf].pct >= threshold for wf in WORKFLOWS)

    blocking_gaps: list[dict[str, str]] = []
    if not satisfied:
        for wf in WORKFLOWS:
            wc = wf_coverages[wf]
            if wc.pct < threshold:
                for q in buckets[wf]:
                    if q.get("status") != "GREEN":
                        blocking_gaps.append(
                            {
                                "workflow": wf,
                                "question_text": q.get("text", ""),
                                "target_field": q.get("target_field", ""),
                            }
                        )

    return CoverageResult(
        wf1=wf_coverages["WF1"],
        wf2=wf_coverages["WF2"],
        wf3=wf_coverages["WF3"],
        satisfied=satisfied,
        blocking_gaps=blocking_gaps,
    )
