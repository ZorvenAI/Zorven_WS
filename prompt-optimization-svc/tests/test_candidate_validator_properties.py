"""Hypothesis property tests for candidate validation (US-032)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.candidate_validator import (
    VALID_DECISIONS,
    compute_aggregate_score,
    split_holdout,
    validate_candidate,
)


class TestSplitHoldoutProperties:
    @given(st.lists(st.integers(), min_size=0, max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_preserves_total_length(self, examples):
        train, holdout = split_holdout(examples)
        assert len(train) + len(holdout) == len(examples)

    @given(st.lists(st.integers(), min_size=10, max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_holdout_approximately_20pct(self, examples):
        _, holdout = split_holdout(examples)
        expected = int(len(examples) * 0.2)
        assert abs(len(holdout) - expected) <= 1


class TestAggregateScoreProperties:
    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=5),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=10,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_always_in_range(self, scores):
        result = compute_aggregate_score(scores)
        assert 0.0 <= result <= 1.0


class TestValidateCandidateProperties:
    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=5),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=5,
        ),
        st.dictionaries(
            st.text(min_size=1, max_size=5),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_always_valid_decision(self, cand, prod):
        result = validate_candidate(cand, prod)
        assert result.decision in VALID_DECISIONS

    @given(
        st.floats(min_value=0.01, max_value=0.99, allow_nan=False),
    )
    @settings(max_examples=30, deadline=None)
    def test_below_5pct_always_rejected(self, base):
        prod = {"s1": base}
        # 4% improvement
        cand = {"s1": base * 1.04}
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"
