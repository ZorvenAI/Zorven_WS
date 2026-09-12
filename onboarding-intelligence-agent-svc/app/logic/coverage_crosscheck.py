"""J-02 — Coverage cross-validation between full and incremental values.

AC-3: SKL-OIA-09 full-mode coverage must agree with G-06's incremental values
within a configurable tolerance. Differences are logged at WARNING so operators
can investigate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.logging import get_logger
from app.logic.coverage import CoverageResult, WORKFLOWS

logger = get_logger(__name__)


@dataclass
class CoverageDifference:
    """A single workflow where full and incremental coverage diverge."""

    workflow: str
    full_pct: float
    incremental_pct: float
    delta: float
    cause: str


def crosscheck_coverage(
    full_result: CoverageResult,
    incremental: dict[str, Any] | None,
    tolerance: float = 0.05,
) -> list[CoverageDifference]:
    """Compare full coverage (from compute_coverage) with stored incremental values.

    Returns differences that exceed the tolerance.
    """
    if incremental is None:
        logger.info(
            "coverage_crosscheck_no_incremental",
            detail="no incremental coverage stored — skipping cross-validation",
        )
        return []

    full_map = full_result.as_map()
    differences: list[CoverageDifference] = []

    for wf in WORKFLOWS:
        full_pct = full_map.get(wf, 0.0)
        inc_pct = _parse_float(incremental.get(wf, 0.0))

        delta = abs(full_pct - inc_pct)
        if delta > tolerance:
            cause = _infer_cause(full_pct, inc_pct)
            diff = CoverageDifference(
                workflow=wf,
                full_pct=round(full_pct, 4),
                incremental_pct=round(inc_pct, 4),
                delta=round(delta, 4),
                cause=cause,
            )
            differences.append(diff)

            logger.warning(
                "coverage_crosscheck_difference",
                workflow=wf,
                full_pct=diff.full_pct,
                incremental_pct=diff.incremental_pct,
                delta=diff.delta,
                cause=cause,
            )

    if not differences:
        logger.info(
            "coverage_crosscheck_ok",
            detail="full and incremental coverage agree within tolerance",
            tolerance=tolerance,
        )

    return differences


def _infer_cause(full_pct: float, inc_pct: float) -> str:
    """Best-effort inference of why coverage diverged."""
    if full_pct > inc_pct:
        return "full assessment found more answered questions than incremental tracking"
    return "incremental tracking reported higher coverage than full reassessment"


def _parse_float(value: Any) -> float:
    """Safely parse a float from a Redis hash value."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
