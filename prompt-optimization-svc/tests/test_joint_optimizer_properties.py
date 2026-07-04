"""Hypothesis property tests for joint optimizer groups (US-019)."""

from hypothesis import given, settings as hyp_settings
from hypothesis import strategies as st

from app.logic.prompt_naming import validate_prompt_name
from app.registries.optimization_groups import OPTIMIZATION_GROUPS

_group_names = st.sampled_from(sorted(OPTIMIZATION_GROUPS.keys()))


class TestGroupProperties:

    @given(group_name=_group_names)
    @hyp_settings(max_examples=10)
    def test_all_prompt_names_pass_validation(self, group_name):
        """Every prompt in every group passes §3.1 naming validation."""
        group = OPTIMIZATION_GROUPS[group_name]
        for pn in group.prompt_names:
            parts = validate_prompt_name(pn)
            assert parts is not None

    @given(group_name=_group_names)
    @hyp_settings(max_examples=10)
    def test_agent_codes_match_prompt_names(self, group_name):
        """Each group's agent_codes match the agents in prompt_names."""
        group = OPTIMIZATION_GROUPS[group_name]
        prompt_agents = set()
        for pn in group.prompt_names:
            parts = validate_prompt_name(pn)
            prompt_agents.add(parts.agent_code)
        assert prompt_agents == set(group.agent_codes)

    @given(group_name=_group_names)
    @hyp_settings(max_examples=10)
    def test_workflow_matches_prompt_names(self, group_name):
        """Group workflow matches all prompt name workflows."""
        group = OPTIMIZATION_GROUPS[group_name]
        for pn in group.prompt_names:
            parts = validate_prompt_name(pn)
            assert parts.workflow == group.workflow

    @given(group_name=_group_names)
    @hyp_settings(max_examples=10)
    def test_no_duplicate_prompts(self, group_name):
        """No duplicate prompt names in a group."""
        group = OPTIMIZATION_GROUPS[group_name]
        assert len(group.prompt_names) == len(set(group.prompt_names))

    @given(group_name=_group_names)
    @hyp_settings(max_examples=10)
    def test_group_has_description(self, group_name):
        """Every group has a non-empty description."""
        group = OPTIMIZATION_GROUPS[group_name]
        assert len(group.description) > 0
