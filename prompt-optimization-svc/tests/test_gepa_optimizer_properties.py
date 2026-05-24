"""Hypothesis property tests for GEPA optimizer budgets (US-017)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.registries.optimization_budgets import AGENT_BUDGETS, DEFAULT_BUDGET, get_budget

_known_agents = st.sampled_from(sorted(AGENT_BUDGETS.keys()))
_random_strings = st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz")


class TestGetBudgetProperties:

    @given(agent=_known_agents)
    @hyp_settings(max_examples=30)
    def test_known_agent_returns_positive(self, agent):
        """Known agents always get a positive budget."""
        assert get_budget(agent) > 0

    @given(agent=_random_strings)
    @hyp_settings(max_examples=50)
    def test_any_string_returns_positive(self, agent):
        """Any agent code returns a positive budget (known or default)."""
        result = get_budget(agent)
        assert result > 0

    @given(agent=_random_strings)
    @hyp_settings(max_examples=30)
    def test_unknown_agent_gets_default(self, agent):
        """Unknown agents get DEFAULT_BUDGET."""
        if agent.lower() not in AGENT_BUDGETS:
            assert get_budget(agent) == DEFAULT_BUDGET

    @given(agent=_known_agents)
    @hyp_settings(max_examples=15)
    def test_case_insensitive(self, agent):
        """Budget lookup is case-insensitive."""
        assert get_budget(agent.upper()) == get_budget(agent.lower())
