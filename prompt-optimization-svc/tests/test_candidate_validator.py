"""Unit tests for candidate validation (US-032, OPT-03/OPT-04)."""

from app.logic.candidate_validator import (
    ValidationResult,
    compute_aggregate_score,
    split_holdout,
    validate_candidate,
)


class TestSplitHoldout:
    """AC-1: Validation uses a held-out 20% slice."""

    def test_100_examples_80_20_split(self):
        examples = list(range(100))
        train, holdout = split_holdout(examples)
        assert len(train) == 80
        assert len(holdout) == 20

    def test_deterministic(self):
        examples = list(range(50))
        t1, h1 = split_holdout(examples, seed=42)
        t2, h2 = split_holdout(examples, seed=42)
        assert t1 == t2
        assert h1 == h2

    def test_different_seed_different_split(self):
        examples = list(range(50))
        _, h1 = split_holdout(examples, seed=42)
        _, h2 = split_holdout(examples, seed=99)
        assert h1 != h2

    def test_empty_list(self):
        train, holdout = split_holdout([])
        assert train == []
        assert holdout == []

    def test_small_list_at_least_1_holdout(self):
        examples = list(range(3))
        train, holdout = split_holdout(examples)
        assert len(holdout) >= 1

    def test_preserves_all_elements(self):
        examples = list(range(50))
        train, holdout = split_holdout(examples)
        assert sorted(train + holdout) == examples

    def test_custom_holdout_pct(self):
        examples = list(range(100))
        train, holdout = split_holdout(examples, holdout_pct=0.3)
        assert len(holdout) == 30
        assert len(train) == 70


class TestComputeAggregateScore:
    def test_simple_mean(self):
        scores = {"scorer_a": 0.8, "scorer_b": 0.6}
        assert compute_aggregate_score(scores) == 0.7

    def test_empty_dict(self):
        assert compute_aggregate_score({}) == 0.0

    def test_single_scorer(self):
        assert compute_aggregate_score({"s1": 0.9}) == 0.9

    def test_all_perfect(self):
        scores = {"a": 1.0, "b": 1.0, "c": 1.0}
        assert compute_aggregate_score(scores) == 1.0

    def test_all_zero(self):
        scores = {"a": 0.0, "b": 0.0}
        assert compute_aggregate_score(scores) == 0.0


class TestValidateCandidate:
    """AC-2 (OPT-03) and AC-3 (OPT-04)."""

    def test_10pct_improvement_canary(self):
        prod = {"s1": 0.70, "s2": 0.70}
        cand = {"s1": 0.80, "s2": 0.75}
        result = validate_candidate(cand, prod)
        assert result.decision == "CANARY"
        assert result.passed is True

    def test_3pct_improvement_rejected(self):
        """AC-2: < 5% → REJECTED."""
        prod = {"s1": 0.80, "s2": 0.80}
        cand = {"s1": 0.82, "s2": 0.82}  # ~2.5% improvement
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"
        assert result.passed is False

    def test_0pct_improvement_rejected(self):
        prod = {"s1": 0.80, "s2": 0.80}
        cand = {"s1": 0.80, "s2": 0.80}
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"

    def test_negative_improvement_rejected(self):
        prod = {"s1": 0.80, "s2": 0.80}
        cand = {"s1": 0.70, "s2": 0.70}
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"

    def test_6pct_improvement_with_4pct_regression_pending(self):
        """AC-3: individual regression > 3% → PENDING_APPROVAL."""
        prod = {"s1": 0.70, "s2": 0.80}
        cand = {"s1": 0.85, "s2": 0.76}  # s2 regresses 5%
        result = validate_candidate(cand, prod)
        assert result.decision == "PENDING_APPROVAL"
        assert "s2" in result.scorer_regressions

    def test_6pct_improvement_no_regressions_canary(self):
        prod = {"s1": 0.70, "s2": 0.70}
        cand = {"s1": 0.76, "s2": 0.76}  # ~8.6% improvement, no regression
        result = validate_candidate(cand, prod)
        assert result.decision == "CANARY"

    def test_just_above_5pct_threshold_canary(self):
        """Just above 5% improvement should pass."""
        prod = {"s1": 0.80}
        cand = {"s1": 0.85}  # 6.25% improvement
        result = validate_candidate(cand, prod)
        assert result.decision == "CANARY"

    def test_just_below_5pct_threshold_rejected(self):
        """Just below 5% improvement should fail."""
        prod = {"s1": 0.80}
        cand = {"s1": 0.838}  # 4.75% improvement
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"

    def test_2pct_regression_no_flag(self):
        """2% regression should NOT flag (>3% needed)."""
        prod = {"s1": 0.50, "s2": 1.00}
        cand = {"s1": 0.80, "s2": 0.98}  # s2 regresses 2%, s1 improves 60%
        result = validate_candidate(cand, prod)
        assert "s2" not in result.scorer_regressions

    def test_result_has_all_fields(self):
        prod = {"s1": 0.80}
        cand = {"s1": 0.90}
        result = validate_candidate(cand, prod)
        assert isinstance(result, ValidationResult)
        assert isinstance(result.aggregate_improvement, float)
        assert isinstance(result.scorer_regressions, dict)
        assert isinstance(result.candidate_scores, dict)
        assert isinstance(result.production_scores, dict)

    def test_production_zero_candidate_positive(self):
        prod = {"s1": 0.0}
        cand = {"s1": 0.5}
        result = validate_candidate(cand, prod)
        assert result.decision == "CANARY"

    def test_both_zero(self):
        prod = {"s1": 0.0}
        cand = {"s1": 0.0}
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"

    def test_custom_thresholds(self):
        prod = {"s1": 0.80}
        cand = {"s1": 0.82}  # 2.5% improvement
        # With 2% threshold, should pass
        result = validate_candidate(cand, prod, improvement_threshold=0.02)
        assert result.decision == "CANARY"

    def test_multiple_regressions(self):
        prod = {"s1": 0.60, "s2": 0.80, "s3": 0.80}
        cand = {"s1": 0.95, "s2": 0.70, "s3": 0.70}  # agg improves ~7%, s2/s3 regress
        result = validate_candidate(cand, prod)
        assert result.decision == "PENDING_APPROVAL"
        assert len(result.scorer_regressions) == 2


class TestConfigConstants:
    def test_holdout_pct(self):
        from app.core.config import settings

        assert settings.VALIDATION_HOLDOUT_PCT == 0.2

    def test_improvement_threshold(self):
        from app.core.config import settings

        assert settings.VALIDATION_IMPROVEMENT_THRESHOLD == 0.05

    def test_regression_threshold(self):
        from app.core.config import settings

        assert settings.VALIDATION_REGRESSION_THRESHOLD == 0.03
