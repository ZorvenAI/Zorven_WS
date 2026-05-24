"""Hypothesis property tests for run lifecycle (US-020)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.logic.run_lifecycle import (
    InvalidRunTransitionError,
    RunLifecycleManager,
    RunState,
    TERMINAL_STATES,
    VALID_RUN_TRANSITIONS,
)

_all_states = st.sampled_from(list(RunState))
_terminal = st.sampled_from(list(TERMINAL_STATES))


class TestRunTransitionProperties:

    @given(from_state=_all_states, to_state=_all_states)
    @hyp_settings(max_examples=200)
    def test_transition_either_valid_or_raises(self, from_state, to_state):
        try:
            result = RunLifecycleManager().validate_transition(
                from_state, to_state
            )
            assert result is True
            assert to_state in VALID_RUN_TRANSITIONS[from_state]
        except InvalidRunTransitionError:
            assert to_state not in VALID_RUN_TRANSITIONS.get(
                from_state, set()
            )

    @given(from_state=_terminal, to_state=_all_states)
    @hyp_settings(max_examples=50)
    def test_no_transitions_from_terminal(self, from_state, to_state):
        try:
            RunLifecycleManager().validate_transition(from_state, to_state)
            assert False, f"Should not allow {from_state} → {to_state}"
        except InvalidRunTransitionError:
            pass

    @given(state=_all_states)
    @hyp_settings(max_examples=20)
    def test_is_terminal_is_deterministic(self, state):
        r1 = RunLifecycleManager.is_terminal(state)
        r2 = RunLifecycleManager.is_terminal(state)
        assert r1 == r2
        assert isinstance(r1, bool)

    @given(state=_all_states)
    @hyp_settings(max_examples=20)
    def test_active_and_terminal_are_complements(self, state):
        is_t = RunLifecycleManager.is_terminal(state)
        is_a = RunLifecycleManager.is_active(state)
        assert is_t != is_a, f"{state} is both terminal and active"

    def test_all_states_in_transitions_map(self):
        for state in RunState:
            assert state in VALID_RUN_TRANSITIONS
