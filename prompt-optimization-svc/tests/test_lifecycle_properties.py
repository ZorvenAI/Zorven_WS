"""Hypothesis property tests for lifecycle state machine (US-008)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.logic.lifecycle import (
    InvalidTransitionError,
    PromptState,
    VALID_TRANSITIONS,
    SERVABLE_STATES,
    PromptLifecycleManager,
)

_all_states = st.sampled_from(list(PromptState))
_terminal_states = st.sampled_from([
    PromptState.ARCHIVED, PromptState.REJECTED, PromptState.ROLLED_BACK,
])


class TestStateTransitionProperties:

    @given(from_state=_all_states, to_state=_all_states)
    @hyp_settings(max_examples=100)
    def test_transition_either_valid_or_raises(self, from_state, to_state):
        """Every (from, to) pair either succeeds or raises InvalidTransitionError."""
        try:
            result = PromptLifecycleManager(None).validate_transition(
                from_state, to_state
            )
            assert result is True
            assert to_state in VALID_TRANSITIONS[from_state]
        except InvalidTransitionError:
            assert to_state not in VALID_TRANSITIONS.get(from_state, set())

    @given(from_state=_terminal_states, to_state=_all_states)
    @hyp_settings(max_examples=30)
    def test_no_transitions_from_terminal(self, from_state, to_state):
        """Terminal states (ARCHIVED, REJECTED, ROLLED_BACK) have no outgoing transitions."""
        try:
            PromptLifecycleManager(None).validate_transition(
                from_state, to_state
            )
            assert False, f"Should not allow {from_state} -> {to_state}"
        except InvalidTransitionError:
            pass

    @given(state=_all_states)
    @hyp_settings(max_examples=20)
    def test_servable_is_deterministic(self, state):
        """is_servable returns consistent bool for any state."""
        result = PromptLifecycleManager.is_servable(state)
        assert isinstance(result, bool)
        assert result == (state in SERVABLE_STATES)

    def test_valid_transitions_covers_all_states(self):
        """Every PromptState is a key in VALID_TRANSITIONS."""
        for state in PromptState:
            assert state in VALID_TRANSITIONS
