"""Latency, diarization and cost measurement for STT v2 spike.

Collects per-utterance measurements as JSONL, computes statistics,
and generates the markdown report for A-01.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Measurement:
    """A single utterance latency measurement."""

    utterance_id: int
    onset_ts_ms: float
    first_partial_ts_ms: float
    latency_ms: float
    text: str
    is_final: bool
    speaker_tag: int
    recognizer: str


@dataclass
class LatencyStats:
    """Aggregated latency statistics for a recognizer configuration."""

    recognizer: str
    sample_count: int
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float
    verdict: str  # PASS | MARGINAL | FAIL


@dataclass
class DiarizationResult:
    """Diarization accuracy results."""

    total_segments: int
    correct_segments: int
    misattributed_segments: int
    misattribution_rate: float
    reconnect_labels_stable: bool | None = None


@dataclass
class CostEstimate:
    """Per-hour cost estimate."""

    streaming_cost_per_hour: float
    diarization_increment: float
    batch_backfill_cost: float
    total_per_hour: float
    price_per_15s: float
    price_source: str  # "billing" or "published"


LATENCY_BUDGET_MS = 2000


# ---------------------------------------------------------------------------
# JSONL I/O
# ---------------------------------------------------------------------------


def create_jsonl_path(output_dir: str = ".") -> Path:
    """Create a timestamped JSONL file path."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(output_dir) / f"measurements_{ts}.jsonl"


def write_measurement(path: Path, m: Measurement) -> None:
    """Append a single measurement to a JSONL file."""
    with open(path, "a") as f:
        f.write(json.dumps(asdict(m)) + "\n")


def read_measurements(path: Path) -> list[Measurement]:
    """Read all measurements from a JSONL file."""
    measurements: list[Measurement] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            measurements.append(Measurement(**data))
    return measurements


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_stats(
    measurements: list[Measurement],
    recognizer: str | None = None,
) -> LatencyStats:
    """Compute latency percentiles and verdict for a set of measurements.

    Args:
        measurements: List of measurements to analyse.
        recognizer: If provided, filter to this recognizer only.

    Returns:
        LatencyStats with p50, p95, min, max, mean, and verdict.

    Raises:
        ValueError: If no measurements match the filter.
    """
    if recognizer:
        measurements = [m for m in measurements if m.recognizer == recognizer]

    if not measurements:
        raise ValueError(
            f"No measurements found"
            + (f" for recognizer '{recognizer}'" if recognizer else "")
        )

    latencies = np.array([m.latency_ms for m in measurements], dtype=np.float64)
    p50 = float(np.percentile(latencies, 50))
    p95 = float(np.percentile(latencies, 95))
    min_ms = float(np.min(latencies))
    max_ms = float(np.max(latencies))
    mean_ms = float(np.mean(latencies))

    verdict = _compute_verdict(p50, p95)

    return LatencyStats(
        recognizer=recognizer or "all",
        sample_count=len(measurements),
        p50_ms=round(p50, 1),
        p95_ms=round(p95, 1),
        min_ms=round(min_ms, 1),
        max_ms=round(max_ms, 1),
        mean_ms=round(mean_ms, 1),
        verdict=verdict,
    )


def _compute_verdict(p50: float, p95: float) -> str:
    """Determine PASS/MARGINAL/FAIL against the 2-second budget.

    PASS:     p95 <= 2000ms
    MARGINAL: p50 <= 2000ms < p95
    FAIL:     p50 > 2000ms
    """
    if p95 <= LATENCY_BUDGET_MS:
        return "PASS"
    elif p50 <= LATENCY_BUDGET_MS:
        return "MARGINAL"
    else:
        return "FAIL"


# ---------------------------------------------------------------------------
# Diarization accuracy
# ---------------------------------------------------------------------------


@dataclass
class SegmentLabel:
    """A segment with predicted and ground-truth speaker labels."""

    segment_id: int
    predicted_speaker: int
    actual_speaker: int


def compute_diarization_accuracy(
    segments: list[SegmentLabel],
    reconnect_labels_stable: bool | None = None,
) -> DiarizationResult:
    """Compute diarization misattribution rate.

    Args:
        segments: List of segments with predicted and actual speaker labels.
        reconnect_labels_stable: Whether labels remained stable across a
            mid-stream reconnect (None if not tested).

    Returns:
        DiarizationResult with misattribution rate.

    Raises:
        ValueError: If segments list is empty.
    """
    if not segments:
        raise ValueError("No segments provided for diarization accuracy")

    correct = sum(1 for s in segments if s.predicted_speaker == s.actual_speaker)
    misattributed = len(segments) - correct
    rate = misattributed / len(segments)

    return DiarizationResult(
        total_segments=len(segments),
        correct_segments=correct,
        misattributed_segments=misattributed,
        misattribution_rate=round(rate, 4),
        reconnect_labels_stable=reconnect_labels_stable,
    )


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------


def compute_cost(
    duration_s: float,
    price_per_15s: float,
    diarization_surcharge_per_15s: float = 0.0,
    reconnect_loss_fraction: float = 0.05,
    batch_price_per_15s: float | None = None,
    price_source: str = "published",
) -> CostEstimate:
    """Calculate per-hour cost for STT v2 streaming.

    Args:
        duration_s: Duration to calculate for (typically 3600 for one hour).
        price_per_15s: Base streaming price per 15-second increment.
        diarization_surcharge_per_15s: Extra charge for diarization (if any).
        reconnect_loss_fraction: Fraction of audio lost to reconnects (batch backfill).
        batch_price_per_15s: Batch recognition price per 15s (for backfill).
            If None, uses price_per_15s * 0.667 as estimate.
        price_source: "billing" or "published".

    Returns:
        CostEstimate with itemised costs.
    """
    intervals = math.ceil(duration_s / 15)
    streaming_cost = intervals * price_per_15s
    diarization_cost = intervals * diarization_surcharge_per_15s

    if batch_price_per_15s is None:
        batch_price_per_15s = price_per_15s * 0.667

    backfill_duration = duration_s * reconnect_loss_fraction
    backfill_intervals = math.ceil(backfill_duration / 15)
    backfill_cost = backfill_intervals * batch_price_per_15s

    total = streaming_cost + diarization_cost + backfill_cost

    return CostEstimate(
        streaming_cost_per_hour=round(streaming_cost, 4),
        diarization_increment=round(diarization_cost, 4),
        batch_backfill_cost=round(backfill_cost, 4),
        total_per_hour=round(total, 4),
        price_per_15s=price_per_15s,
        price_source=price_source,
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    stats_fixed: LatencyStats,
    stats_auto: LatencyStats | None,
    diarization: DiarizationResult | None,
    cost: CostEstimate,
    environment: dict[str, str] | None = None,
) -> str:
    """Generate the A-01 measurement note as markdown.

    Args:
        stats_fixed: Latency stats for the fixed-language recognizer.
        stats_auto: Latency stats for the multi-language recognizer (optional).
        diarization: Diarization accuracy results (optional).
        cost: Cost estimate.
        environment: Optional dict of environment details (os, browser, etc.).

    Returns:
        Markdown string for docs/spikes/A-01-stt-v2-measurement-note.md.
    """
    lines: list[str] = []
    lines.append("# A-01 — STT v2 Streaming Latency Measurement Note")
    lines.append("")
    lines.append(f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"**Spike**: A-01 — Google STT v2 streaming latency and diarization")
    lines.append("")

    # Environment
    if environment:
        lines.append("## Environment")
        lines.append("")
        for key, value in environment.items():
            lines.append(f"- **{key}**: {value}")
        lines.append("")

    # Latency
    lines.append("## Latency Results")
    lines.append("")
    lines.append(
        "| Recognizer | Samples | p50 (ms) | p95 (ms) | Min (ms) | Max (ms) "
        "| Mean (ms) | Verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for s in [stats_fixed] + ([stats_auto] if stats_auto else []):
        lines.append(
            f"| {s.recognizer} | {s.sample_count} | {s.p50_ms} | {s.p95_ms} "
            f"| {s.min_ms} | {s.max_ms} | {s.mean_ms} | **{s.verdict}** |"
        )
    lines.append("")
    lines.append(f"Budget: {LATENCY_BUDGET_MS}ms. ")
    lines.append("Verdict rules: PASS = p95 ≤ budget, MARGINAL = p50 ≤ budget < p95, "
                  "FAIL = p50 > budget.")
    lines.append("")

    # Diarization
    if diarization:
        lines.append("## Diarization Results")
        lines.append("")
        lines.append(f"- **Total segments**: {diarization.total_segments}")
        lines.append(f"- **Correct**: {diarization.correct_segments}")
        lines.append(f"- **Misattributed**: {diarization.misattributed_segments}")
        lines.append(
            f"- **Misattribution rate**: {diarization.misattribution_rate:.2%}"
        )
        if diarization.reconnect_labels_stable is not None:
            stability = (
                "Stable" if diarization.reconnect_labels_stable else "Unstable"
            )
            lines.append(f"- **Reconnect label stability**: {stability}")
        lines.append("")

    # Cost
    lines.append("## Cost Estimate")
    lines.append("")
    lines.append(f"- **Price per 15s**: ${cost.price_per_15s:.4f} "
                  f"(source: {cost.price_source})")
    lines.append(
        f"- **Streaming cost per hour**: ${cost.streaming_cost_per_hour:.2f}"
    )
    lines.append(f"- **Diarization increment**: ${cost.diarization_increment:.2f}")
    lines.append(f"- **Batch backfill cost (5%)**: ${cost.batch_backfill_cost:.2f}")
    lines.append(f"- **Total per meeting hour**: **${cost.total_per_hour:.2f}**")
    lines.append("")

    # Language comparison
    if stats_auto:
        lines.append("## Language Mode Comparison")
        lines.append("")
        delta_p50 = stats_auto.p50_ms - stats_fixed.p50_ms
        delta_p95 = stats_auto.p95_ms - stats_fixed.p95_ms
        lines.append(f"- **p50 delta** (auto − fixed): {delta_p50:+.1f}ms")
        lines.append(f"- **p95 delta** (auto − fixed): {delta_p95:+.1f}ms")
        lines.append("")

    # Recommendations
    lines.append("## Recommendations")
    lines.append("")
    lines.append("- See `docs/decisions/OD-002-stt-language-mode.md` for the "
                  "language mode decision.")
    lines.append("- F-05 and F-06 should reference this note for latency budgets "
                  "and cost projections.")
    lines.append("")

    return "\n".join(lines)
