"""Turns a measurement JSONL into percentiles and an explicit verdict.

Mirrors ``spike-stt-v2/measurement.py`` so the two spike notes report numbers
the same way: p50/p95 against a stated budget, with PASS / MARGINAL / FAIL
decided by rule rather than by narrative.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Verdict:
    name: str
    samples: int
    p50_ms: float | None
    p95_ms: float | None
    min_ms: float | None
    max_ms: float | None
    mean_ms: float | None
    budget_ms: float
    verdict: str


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Deterministic and dependency-free."""
    if not values:
        raise ValueError("no samples")
    if not 0 < pct <= 100:
        raise ValueError("pct must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(1, rank) - 1]


def verdict_for(p50: float | None, p95: float | None, budget_ms: float) -> str:
    """PASS if p95 within budget, MARGINAL if only p50 is, else FAIL."""
    if p50 is None or p95 is None:
        return "NO DATA"
    if p95 <= budget_ms:
        return "PASS"
    if p50 <= budget_ms:
        return "MARGINAL"
    return "FAIL"


def summarise(name: str, samples_ms: list[float], budget_ms: float) -> Verdict:
    if not samples_ms:
        return Verdict(name, 0, None, None, None, None, None, budget_ms, "NO DATA")
    p50 = percentile(samples_ms, 50)
    p95 = percentile(samples_ms, 95)
    return Verdict(
        name=name,
        samples=len(samples_ms),
        p50_ms=round(p50, 1),
        p95_ms=round(p95, 1),
        min_ms=round(min(samples_ms), 1),
        max_ms=round(max(samples_ms), 1),
        mean_ms=round(sum(samples_ms) / len(samples_ms), 1),
        budget_ms=budget_ms,
        verdict=verdict_for(p50, p95, budget_ms),
    )


def load_rtts(path: Path, event: str = "rtt") -> list[float]:
    """Read ``rtt_ms`` values for one event kind out of a measurement file."""
    out: list[float] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("event") == event and record.get("rtt_ms") is not None:
            out.append(float(record["rtt_ms"]))
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Summarise an A-02 run")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--budget-ms", type=float, default=2000.0)
    parser.add_argument("--name", default="frame round-trip")
    args = parser.parse_args()

    result = summarise(args.name, load_rtts(args.jsonl), args.budget_ms)
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
