"""Shared fixtures for spike-stt-v2 tests."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from measurement import (
    CostEstimate,
    DiarizationResult,
    LatencyStats,
    Measurement,
    SegmentLabel,
    write_measurement,
)


# ---------------------------------------------------------------------------
# Fixtures — Measurement data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_measurements() -> list[Measurement]:
    """A list of 10 measurements with known latency values."""
    return [
        Measurement(
            utterance_id=i + 1,
            onset_ts_ms=1000.0 * i,
            first_partial_ts_ms=1000.0 * i + latency,
            latency_ms=latency,
            text=f"utterance {i + 1}",
            is_final=False,
            speaker_tag=1 if i % 2 == 0 else 2,
            recognizer="oia-spike-en-us",
        )
        for i, latency in enumerate(
            [800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700]
        )
    ]


@pytest.fixture
def passing_measurements() -> list[Measurement]:
    """Measurements that should produce a PASS verdict (p95 <= 2000)."""
    return [
        Measurement(
            utterance_id=i + 1,
            onset_ts_ms=1000.0 * i,
            first_partial_ts_ms=1000.0 * i + latency,
            latency_ms=latency,
            text=f"utterance {i + 1}",
            is_final=False,
            speaker_tag=1,
            recognizer="oia-spike-en-us",
        )
        for i, latency in enumerate([500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400])
    ]


@pytest.fixture
def marginal_measurements() -> list[Measurement]:
    """Measurements that should produce a MARGINAL verdict (p50 <= 2000 < p95)."""
    return [
        Measurement(
            utterance_id=i + 1,
            onset_ts_ms=1000.0 * i,
            first_partial_ts_ms=1000.0 * i + latency,
            latency_ms=latency,
            text=f"utterance {i + 1}",
            is_final=False,
            speaker_tag=1,
            recognizer="oia-spike-en-us",
        )
        for i, latency in enumerate(
            [500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 5000]
        )
    ]


@pytest.fixture
def failing_measurements() -> list[Measurement]:
    """Measurements that should produce a FAIL verdict (p50 > 2000)."""
    return [
        Measurement(
            utterance_id=i + 1,
            onset_ts_ms=1000.0 * i,
            first_partial_ts_ms=1000.0 * i + latency,
            latency_ms=latency,
            text=f"utterance {i + 1}",
            is_final=False,
            speaker_tag=1,
            recognizer="oia-spike-en-us",
        )
        for i, latency in enumerate(
            [2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800, 2900, 3000]
        )
    ]


@pytest.fixture
def jsonl_file(sample_measurements: list[Measurement], tmp_path: Path) -> Path:
    """Write sample measurements to a temporary JSONL file."""
    path = tmp_path / "test_measurements.jsonl"
    for m in sample_measurements:
        write_measurement(path, m)
    return path


@pytest.fixture
def perfect_segments() -> list[SegmentLabel]:
    """Segments where all predictions match ground truth."""
    return [
        SegmentLabel(segment_id=i, predicted_speaker=s, actual_speaker=s)
        for i, s in enumerate([1, 2, 1, 2, 1, 2, 1, 2, 1, 2])
    ]


@pytest.fixture
def imperfect_segments() -> list[SegmentLabel]:
    """Segments with 3 out of 10 misattributed."""
    predicted = [1, 2, 1, 2, 1, 2, 1, 2, 1, 2]
    actual = [1, 2, 2, 2, 1, 1, 1, 2, 2, 2]  # 3 wrong: idx 2, 5, 8
    return [
        SegmentLabel(segment_id=i, predicted_speaker=p, actual_speaker=a)
        for i, (p, a) in enumerate(zip(predicted, actual))
    ]


# ---------------------------------------------------------------------------
# Fixtures — STT config
# ---------------------------------------------------------------------------


@pytest.fixture
def gcp_project_id() -> str:
    """GCP project ID from environment, skip if not set."""
    project_id = os.environ.get("OIA_SPIKE_PROJECT_ID", "")
    if not project_id:
        pytest.skip("OIA_SPIKE_PROJECT_ID not set — skipping integration test")
    return project_id
