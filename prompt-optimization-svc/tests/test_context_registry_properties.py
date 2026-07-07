"""Hypothesis property tests for context variable registry (US-031)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.registries.context_variables import (
    SHARED_VARIABLES,
    get_agent_variable_names,
    get_variables_for_agent,
    validate_template_against_registry,
)
from app.registries.prompt_catalog import AGENT_PORTS


class TestRegistryProperties:
    @given(st.sampled_from(sorted(AGENT_PORTS.keys())))
    @settings(max_examples=15, deadline=None)
    def test_every_agent_has_at_least_5_vars(self, agent):
        vars_for = get_variables_for_agent(agent)
        assert len(vars_for) >= 5

    @given(st.sampled_from(sorted(AGENT_PORTS.keys())))
    @settings(max_examples=15, deadline=None)
    def test_all_var_names_start_with_context(self, agent):
        names = get_agent_variable_names(agent)
        for name in names:
            assert name.startswith("context.")

    @given(st.sampled_from(sorted(AGENT_PORTS.keys())))
    @settings(max_examples=15, deadline=None)
    def test_always_includes_shared_variables(self, agent):
        vars_for = get_variables_for_agent(agent)
        agent_names = {v.name for v in vars_for}
        shared_names = {v.name for v in SHARED_VARIABLES}
        assert shared_names.issubset(agent_names)

    @given(st.text(max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_validate_never_raises(self, template):
        violations = validate_template_against_registry(template, "mra")
        assert isinstance(violations, list)
