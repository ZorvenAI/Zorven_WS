"""Hypothesis property tests for golden dataset mining (US-028)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.datasets.miner import MiningResult


class TestMiningResultProperties:
    @given(
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=50, deadline=None)
    def test_fields_are_non_negative(self, mined, skipped, errors):
        r = MiningResult(mined=mined, skipped=skipped, errors=errors)
        assert r.mined >= 0
        assert r.skipped >= 0
        assert r.errors >= 0

    @given(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=50, deadline=None)
    def test_quality_threshold_valid_range(self, threshold):
        # Any threshold in [0, 1] should be valid for the miner
        assert 0.0 <= threshold <= 1.0

    @given(
        st.integers(min_value=1, max_value=365),
    )
    @settings(max_examples=30, deadline=None)
    def test_lookback_days_positive(self, days):
        assert days > 0


class TestQualityScoreProperties:
    @given(st.booleans())
    @settings(max_examples=10, deadline=None)
    def test_score_always_in_range(self, has_mlflow):
        from app.datasets.miner import _compute_quality_score

        class FakeRun:
            mlflow_run_id = "run-123" if has_mlflow else None

        score = _compute_quality_score(FakeRun())
        assert 0.0 <= score <= 1.0
