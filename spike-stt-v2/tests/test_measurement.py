"""Unit and property tests for measurement.py.

No Google Cloud credentials required.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from measurement import (
    LATENCY_BUDGET_MS,
    CostEstimate,
    DiarizationResult,
    LatencyStats,
    Measurement,
    SegmentLabel,
    compute_cost,
    compute_diarization_accuracy,
    compute_stats,
    generate_report,
    read_measurements,
    write_measurement,
    _compute_verdict,
)


# ===================================================================
# Unit tests — compute_stats
# ===================================================================


class TestComputeStatsVerdict:
    def test_pass_verdict(self, passing_measurements: list[Measurement]):
        stats = compute_stats(passing_measurements)
        assert stats.verdict == "PASS"
        assert stats.p95_ms <= LATENCY_BUDGET_MS

    def test_marginal_verdict(self, marginal_measurements: list[Measurement]):
        stats = compute_stats(marginal_measurements)
        assert stats.verdict == "MARGINAL"
        assert stats.p50_ms <= LATENCY_BUDGET_MS
        assert stats.p95_ms > LATENCY_BUDGET_MS

    def test_fail_verdict(self, failing_measurements: list[Measurement]):
        stats = compute_stats(failing_measurements)
        assert stats.verdict == "FAIL"
        assert stats.p50_ms > LATENCY_BUDGET_MS

    def test_empty_data_raises(self):
        with pytest.raises(ValueError, match="No measurements found"):
            compute_stats([])

    def test_single_measurement(self):
        m = Measurement(
            utterance_id=1,
            onset_ts_ms=0,
            first_partial_ts_ms=1500,
            latency_ms=1500,
            text="hello",
            is_final=False,
            speaker_tag=1,
            recognizer="oia-spike-en-us",
        )
        stats = compute_stats([m])
        assert stats.p50_ms == 1500.0
        assert stats.p95_ms == 1500.0
        assert stats.sample_count == 1
        assert stats.verdict == "PASS"

    def test_filter_by_recognizer(self, sample_measurements: list[Measurement]):
        # Add a measurement with a different recognizer
        extra = Measurement(
            utterance_id=99,
            onset_ts_ms=0,
            first_partial_ts_ms=5000,
            latency_ms=5000,
            text="other",
            is_final=False,
            speaker_tag=1,
            recognizer="oia-spike-auto",
        )
        all_m = sample_measurements + [extra]
        stats = compute_stats(all_m, recognizer="oia-spike-en-us")
        assert stats.sample_count == len(sample_measurements)
        assert stats.recognizer == "oia-spike-en-us"

    def test_filter_by_missing_recognizer_raises(self, sample_measurements):
        with pytest.raises(ValueError, match="No measurements found"):
            compute_stats(sample_measurements, recognizer="nonexistent")


# ===================================================================
# Unit tests — diarization accuracy
# ===================================================================


class TestDiarizationAccuracy:
    def test_perfect_accuracy(self, perfect_segments: list[SegmentLabel]):
        result = compute_diarization_accuracy(perfect_segments)
        assert result.misattribution_rate == 0.0
        assert result.correct_segments == 10
        assert result.misattributed_segments == 0

    def test_with_errors(self, imperfect_segments: list[SegmentLabel]):
        result = compute_diarization_accuracy(imperfect_segments)
        assert result.misattributed_segments == 3
        assert result.misattribution_rate == 0.3

    def test_empty_segments_raises(self):
        with pytest.raises(ValueError, match="No segments provided"):
            compute_diarization_accuracy([])

    def test_reconnect_stability_flag(self, perfect_segments):
        result = compute_diarization_accuracy(perfect_segments, reconnect_labels_stable=True)
        assert result.reconnect_labels_stable is True


# ===================================================================
# Unit tests — cost calculation
# ===================================================================


class TestComputeCost:
    def test_one_hour(self):
        cost = compute_cost(
            duration_s=3600,
            price_per_15s=0.006,
        )
        # 3600/15 = 240 intervals
        assert cost.streaming_cost_per_hour == 240 * 0.006
        assert cost.price_source == "published"

    def test_with_diarization_surcharge(self):
        cost = compute_cost(
            duration_s=3600,
            price_per_15s=0.006,
            diarization_surcharge_per_15s=0.001,
        )
        assert cost.diarization_increment == 240 * 0.001

    def test_with_batch_backfill(self):
        cost = compute_cost(
            duration_s=3600,
            price_per_15s=0.006,
            reconnect_loss_fraction=0.05,
            batch_price_per_15s=0.004,
        )
        # Backfill: 3600 * 0.05 = 180s, ceil(180/15) = 12 intervals
        assert cost.batch_backfill_cost == 12 * 0.004


# ===================================================================
# Unit tests — JSONL roundtrip
# ===================================================================


class TestJsonlRoundtrip:
    def test_write_read_roundtrip(
        self, sample_measurements: list[Measurement], tmp_path: Path
    ):
        path = tmp_path / "roundtrip.jsonl"
        for m in sample_measurements:
            write_measurement(path, m)

        loaded = read_measurements(path)
        assert len(loaded) == len(sample_measurements)
        for orig, loaded_m in zip(sample_measurements, loaded):
            assert orig.utterance_id == loaded_m.utterance_id
            assert orig.latency_ms == loaded_m.latency_ms
            assert orig.text == loaded_m.text
            assert orig.recognizer == loaded_m.recognizer


# ===================================================================
# Unit tests — report generation
# ===================================================================


class TestGenerateReport:
    def test_contains_all_sections(self, passing_measurements, perfect_segments):
        stats = compute_stats(passing_measurements)
        diarization = compute_diarization_accuracy(perfect_segments)
        cost = compute_cost(3600, 0.006)

        report = generate_report(
            stats_fixed=stats,
            stats_auto=None,
            diarization=diarization,
            cost=cost,
            environment={"OS": "macOS", "Browser": "Chrome"},
        )

        assert "# A-01" in report
        assert "## Latency Results" in report
        assert "## Diarization Results" in report
        assert "## Cost Estimate" in report
        assert "## Recommendations" in report
        assert "## Environment" in report
        assert "macOS" in report

    def test_with_auto_recognizer(self, passing_measurements):
        stats_fixed = compute_stats(passing_measurements)
        # Create auto measurements with different latencies
        auto_measurements = [
            Measurement(
                utterance_id=m.utterance_id,
                onset_ts_ms=m.onset_ts_ms,
                first_partial_ts_ms=m.first_partial_ts_ms + 100,
                latency_ms=m.latency_ms + 100,
                text=m.text,
                is_final=False,
                speaker_tag=m.speaker_tag,
                recognizer="oia-spike-auto",
            )
            for m in passing_measurements
        ]
        stats_auto = compute_stats(auto_measurements)
        cost = compute_cost(3600, 0.006)

        report = generate_report(
            stats_fixed=stats_fixed,
            stats_auto=stats_auto,
            diarization=None,
            cost=cost,
        )

        assert "## Language Mode Comparison" in report
        assert "p50 delta" in report


# ===================================================================
# Property tests (Hypothesis)
# ===================================================================

positive_floats = st.floats(min_value=1.0, max_value=100000.0, allow_nan=False)


class TestPropertyStats:
    @given(st.lists(positive_floats, min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_p50_between_min_and_max(self, latencies: list[float]):
        measurements = [
            Measurement(
                utterance_id=i,
                onset_ts_ms=0,
                first_partial_ts_ms=lat,
                latency_ms=lat,
                text="t",
                is_final=False,
                speaker_tag=1,
                recognizer="test",
            )
            for i, lat in enumerate(latencies)
        ]
        stats = compute_stats(measurements)
        assert stats.min_ms <= stats.p50_ms <= stats.max_ms

    @given(st.lists(positive_floats, min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_p95_gte_p50(self, latencies: list[float]):
        measurements = [
            Measurement(
                utterance_id=i,
                onset_ts_ms=0,
                first_partial_ts_ms=lat,
                latency_ms=lat,
                text="t",
                is_final=False,
                speaker_tag=1,
                recognizer="test",
            )
            for i, lat in enumerate(latencies)
        ]
        stats = compute_stats(measurements)
        assert stats.p95_ms >= stats.p50_ms

    @given(
        p50=st.floats(min_value=0, max_value=10000, allow_nan=False),
        p95=st.floats(min_value=0, max_value=10000, allow_nan=False),
    )
    @settings(max_examples=100)
    def test_verdict_consistent_with_thresholds(self, p50: float, p95: float):
        # Ensure p95 >= p50 as would be in real data
        if p95 < p50:
            p50, p95 = p95, p50

        verdict = _compute_verdict(p50, p95)

        if p95 <= LATENCY_BUDGET_MS:
            assert verdict == "PASS"
        elif p50 <= LATENCY_BUDGET_MS:
            assert verdict == "MARGINAL"
        else:
            assert verdict == "FAIL"

    @given(
        st.lists(
            st.tuples(st.integers(0, 5), st.integers(0, 5)),
            min_size=1,
            max_size=50,
        )
    )
    @settings(max_examples=50)
    def test_misattribution_rate_bounded_0_1(self, speaker_pairs):
        segments = [
            SegmentLabel(segment_id=i, predicted_speaker=p, actual_speaker=a)
            for i, (p, a) in enumerate(speaker_pairs)
        ]
        result = compute_diarization_accuracy(segments)
        assert 0.0 <= result.misattribution_rate <= 1.0

    @given(
        duration=st.floats(min_value=1.0, max_value=36000.0, allow_nan=False),
        price=st.floats(min_value=0.0001, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=50)
    def test_cost_scales_with_duration(self, duration: float, price: float):
        cost1 = compute_cost(duration, price, reconnect_loss_fraction=0.0, diarization_surcharge_per_15s=0.0)
        cost2 = compute_cost(duration * 2, price, reconnect_loss_fraction=0.0, diarization_surcharge_per_15s=0.0)
        # Due to ceiling, cost2 may be slightly less than 2x cost1 but never more
        assert cost2.streaming_cost_per_hour >= cost1.streaming_cost_per_hour
