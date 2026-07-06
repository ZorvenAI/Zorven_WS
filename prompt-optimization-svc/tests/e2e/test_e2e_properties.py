"""Hypothesis property-based E2E tests (US-060).

Exercises: split_holdout count preservation, deterministic splits,
validate_candidate decisions, canary routing determinism,
lifecycle valid transitions, guardrail chain first failure.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.candidate_validator import split_holdout, validate_candidate
from app.logic.canary_manager import is_canary_request
from app.logic.lifecycle import VALID_TRANSITIONS, PromptState
from app.logic.tenant_isolation import get_mlflow_experiment_name


@pytest.mark.e2e
@pytest.mark.property
class TestProperties:
    """Hypothesis property tests for pipeline invariants."""

    @given(
        examples=st.lists(
            st.fixed_dictionaries(
                {
                    "prompt_name": st.text(min_size=1, max_size=20),
                    "agent_code": st.sampled_from(["mra", "cga", "bpa"]),
                    "input_context": st.just({"context.brand_name": "Test"}),
                    "expected_output": st.text(min_size=1, max_size=50),
                }
            ),
            min_size=2,
            max_size=50,
        )
    )
    @settings(max_examples=30)
    def test_split_holdout_preserves_total_count(self, examples):
        """len(train) + len(holdout) == len(examples) for any input."""
        train, holdout = split_holdout(examples, holdout_pct=0.2, seed=42)
        assert len(train) + len(holdout) == len(examples)
        assert len(holdout) >= 1  # At least 1 holdout

    @given(
        examples=st.lists(
            st.fixed_dictionaries(
                {
                    "prompt_name": st.just("test-prompt"),
                    "input_context": st.just({}),
                    "expected_output": st.text(min_size=1, max_size=20),
                }
            ),
            min_size=2,
            max_size=30,
        ),
        seed=st.integers(min_value=0, max_value=10000),
    )
    @settings(max_examples=20)
    def test_split_holdout_deterministic_with_same_seed(self, examples, seed):
        """Same seed -> same split every time."""
        train1, holdout1 = split_holdout(examples, holdout_pct=0.2, seed=seed)
        train2, holdout2 = split_holdout(examples, holdout_pct=0.2, seed=seed)
        assert train1 == train2
        assert holdout1 == holdout2

    @given(
        scores=st.dictionaries(
            keys=st.sampled_from(
                ["json_compliance", "brand_voice", "pii_safety", "cost_efficiency"]
            ),
            values=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            min_size=1,
            max_size=4,
        )
    )
    @settings(max_examples=30)
    def test_validate_candidate_decision_in_valid_set(self, scores):
        """Decision always in {CANARY, REJECTED, PENDING_APPROVAL}."""
        production_scores = {k: 0.80 for k in scores.keys()}
        result = validate_candidate(
            candidate_scores=scores,
            production_scores=production_scores,
            improvement_threshold=0.05,
            regression_threshold=0.03,
        )
        assert result.decision in ("CANARY", "REJECTED", "PENDING_APPROVAL")

    @given(
        tenant_id=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(codec="utf-8"),
        )
    )
    @settings(max_examples=30)
    def test_canary_routing_deterministic(self, tenant_id):
        """Same tenant_id -> same routing decision every time."""
        result1 = is_canary_request(tenant_id, canary_pct=10)
        result2 = is_canary_request(tenant_id, canary_pct=10)
        assert result1 == result2
        assert isinstance(result1, bool)

    def test_lifecycle_valid_transitions_succeed(self):
        """All declared valid transitions are consistent."""
        for from_state, to_states in VALID_TRANSITIONS.items():
            assert isinstance(from_state, PromptState)
            for to_state in to_states:
                assert isinstance(to_state, PromptState)
                # Valid transition pairs should never have from == to
                assert from_state != to_state

    @given(
        tenant_id=st.one_of(
            st.none(),
            st.text(min_size=0, max_size=30, alphabet="abcdefghijklmnop0123456789_-"),
        )
    )
    @settings(max_examples=30)
    def test_experiment_name_always_valid(self, tenant_id):
        """Experiment name is always a non-empty safe string."""
        name = get_mlflow_experiment_name(tenant_id)
        assert isinstance(name, str)
        assert len(name) > 0
        assert name.startswith("prompt-optimization")
        # No unsafe characters
        for ch in ["@", "/", "..", " ", "\n", "\t"]:
            assert ch not in name
