"""Unit tests for the measurement summariser.

The note's numbers come from this module, so its edge cases matter: a wrong
percentile silently turns a FAIL into a PASS.
"""

import json

import pytest

from harness.analyze import load_rtts, percentile, summarise, verdict_for

pytestmark = pytest.mark.unit


def test_percentile_nearest_rank():
    values = [float(v) for v in range(1, 101)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile(values, 100) == 100.0


def test_percentile_single_sample():
    assert percentile([42.0], 50) == 42.0
    assert percentile([42.0], 95) == 42.0


def test_percentile_is_order_independent():
    assert percentile([9.0, 1.0, 5.0], 50) == percentile([1.0, 5.0, 9.0], 50)


def test_percentile_rejects_empty():
    with pytest.raises(ValueError):
        percentile([], 50)


@pytest.mark.parametrize("pct", [0, -1, 101])
def test_percentile_rejects_out_of_range(pct):
    with pytest.raises(ValueError):
        percentile([1.0], pct)


@pytest.mark.parametrize(
    "p50,p95,expected",
    [
        (10, 100, "PASS"),
        (10, 2000, "PASS"),
        (10, 2001, "MARGINAL"),
        (2001, 5000, "FAIL"),
        (None, None, "NO DATA"),
    ],
)
def test_verdict_rules(p50, p95, expected):
    assert verdict_for(p50, p95, 2000) == expected


def test_summarise_reports_every_statistic():
    result = summarise("round-trip", [1.0, 2.0, 3.0, 4.0], budget_ms=2000)
    assert result.samples == 4
    assert result.min_ms == 1.0 and result.max_ms == 4.0
    assert result.mean_ms == 2.5
    assert result.verdict == "PASS"


def test_summarise_with_no_samples_is_no_data():
    result = summarise("round-trip", [], budget_ms=2000)
    assert result.samples == 0 and result.verdict == "NO DATA"
    assert result.p50_ms is None


def test_load_rtts_filters_by_event(tmp_path):
    path = tmp_path / "m.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"event": "rtt", "rtt_ms": 12.5},
                {"event": "open", "rtt_ms": 300.0},
                {"event": "rtt", "rtt_ms": 15.0},
                {"event": "rtt"},
                {"event": "heartbeat", "sent": 10},
            ]
        )
    )
    assert load_rtts(path) == [12.5, 15.0]
    assert load_rtts(path, event="open") == [300.0]


def test_load_rtts_tolerates_blank_lines(tmp_path):
    path = tmp_path / "m.jsonl"
    path.write_text('\n{"event": "rtt", "rtt_ms": 1.0}\n\n')
    assert load_rtts(path) == [1.0]
