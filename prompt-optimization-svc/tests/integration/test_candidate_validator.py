"""Integration tests for candidate validation (US-032)."""

from app.datasets.golden_seed import GOLDEN_EXAMPLES
from app.logic.candidate_validator import split_holdout, validate_candidate


class TestHoldoutOnRealData:
    def test_split_golden_examples(self):
        train, holdout = split_holdout(GOLDEN_EXAMPLES)
        assert len(train) + len(holdout) == len(GOLDEN_EXAMPLES)
        # ~20% holdout
        expected_holdout = int(len(GOLDEN_EXAMPLES) * 0.2)
        assert abs(len(holdout) - expected_holdout) <= 1

    def test_holdout_non_empty(self):
        _, holdout = split_holdout(GOLDEN_EXAMPLES)
        assert len(holdout) > 0


class TestRealisticValidation:
    def test_clear_improvement_passes(self):
        prod = {"json_compliance": 0.7, "pii_safety": 0.8, "brand_voice": 0.6}
        cand = {"json_compliance": 0.85, "pii_safety": 0.9, "brand_voice": 0.75}
        result = validate_candidate(cand, prod)
        assert result.decision == "CANARY"

    def test_marginal_improvement_rejected(self):
        prod = {"json_compliance": 0.80, "pii_safety": 0.90, "brand_voice": 0.85}
        cand = {"json_compliance": 0.81, "pii_safety": 0.91, "brand_voice": 0.86}
        result = validate_candidate(cand, prod)
        assert result.decision == "REJECTED"

    def test_mixed_results_pending(self):
        prod = {"json_compliance": 0.70, "pii_safety": 0.90, "brand_voice": 0.80}
        cand = {"json_compliance": 0.90, "pii_safety": 0.82, "brand_voice": 0.85}
        result = validate_candidate(cand, prod)
        # pii_safety regressed ~8.9% (>3%) but aggregate improved
        assert result.decision == "PENDING_APPROVAL"
