"""Hypothesis property-based tests for Prometheus metrics (US-048)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.metrics import (
    MLFLOW_HEALTH,
    OPT_RUN_COST,
    OPT_RUN_DURATION,
    PROMPT_CACHE_HIT,
    PROMPT_FALLBACK_USAGE,
    PROMPT_IMPROVEMENT,
    PROMPT_LOAD_LATENCY,
    SCORER_REGRESSION,
    record_optimization_run,
    record_prompt_quality,
)

ALL_METRICS = [
    PROMPT_LOAD_LATENCY,
    PROMPT_CACHE_HIT,
    OPT_RUN_DURATION,
    OPT_RUN_COST,
    PROMPT_IMPROVEMENT,
    SCORER_REGRESSION,
    MLFLOW_HEALTH,
    PROMPT_FALLBACK_USAGE,
]


class TestMetricNamePrefix:
    @pytest.mark.parametrize("metric", ALL_METRICS)
    def test_all_metric_names_prefixed_poi(self, metric):
        assert metric._name.startswith("poi_")


class TestHistogramBucketsSorted:
    @pytest.mark.parametrize(
        "metric",
        [PROMPT_LOAD_LATENCY, OPT_RUN_DURATION, OPT_RUN_COST],
    )
    def test_histogram_buckets_sorted_ascending(self, metric):
        bounds = list(metric._upper_bounds)
        assert bounds == sorted(bounds)
        assert bounds[-1] == float("inf")


class TestRecordFunctionsAcceptFloats:
    @settings(max_examples=50)
    @given(
        duration=st.floats(min_value=0, max_value=1e6),
        cost=st.floats(min_value=0, max_value=1e6),
    )
    def test_record_optimization_run_accepts_positive_floats(self, duration, cost):
        record_optimization_run("test-agent", "test-group", duration, cost)


class TestGaugeSetGetRoundtrip:
    @settings(max_examples=50)
    @given(value=st.floats(min_value=-100, max_value=100))
    def test_prompt_improvement_set_get_roundtrip(self, value):
        PROMPT_IMPROVEMENT.labels(
            agent_code="roundtrip-agent", prompt_name="roundtrip-prompt"
        ).set(value)
        actual = PROMPT_IMPROVEMENT.labels(
            agent_code="roundtrip-agent", prompt_name="roundtrip-prompt"
        )._value.get()
        assert actual == value


class TestCounterOnlyIncrements:
    @settings(max_examples=50)
    @given(n=st.integers(min_value=1, max_value=100))
    def test_cache_hit_counter_never_decreases(self, n):
        label_set = PROMPT_CACHE_HIT.labels(tier="property_test", result="hit")
        before = label_set._value.get()
        for _ in range(n):
            label_set.inc()
        after = label_set._value.get()
        assert after >= before
        assert after - before == n
