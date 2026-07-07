"""Unit tests for optimization groups registry (US-058).

Tests OPTIMIZATION_GROUPS, OptimizationGroup, and get_group() — pure
functions and frozen dataclasses, no external dependencies.
"""

import re
from dataclasses import FrozenInstanceError

import pytest

from app.registries.optimization_groups import (
    OPTIMIZATION_GROUPS,
    OptimizationGroup,
    get_group,
)

ALL_15_AGENTS = {
    "mra",
    "cia",
    "apa",
    "tcia",
    "voca",
    "bpa",
    "baa",
    "bpv",
    "nta",
    "bsa",
    "caa",
    "cga",
    "adpub",
    "coa",
    "ila",
}


class TestOptimizationGroups:
    """Tests for optimization group definitions."""

    def test_four_groups_defined(self):
        assert len(OPTIMIZATION_GROUPS) == 4

    def test_group_names_match_keys(self):
        for key, group in OPTIMIZATION_GROUPS.items():
            assert group.name == key

    def test_get_group_valid(self):
        group = get_group("wf3-creative-pipeline")
        assert isinstance(group, OptimizationGroup)
        assert group.name == "wf3-creative-pipeline"

    def test_get_group_invalid_raises_keyerror(self):
        with pytest.raises(KeyError):
            get_group("nonexistent")

    def test_keyerror_message_includes_valid_groups(self):
        with pytest.raises(KeyError, match="wf3-creative-pipeline"):
            get_group("nonexistent")

    def test_all_groups_are_frozen(self):
        for group in OPTIMIZATION_GROUPS.values():
            assert isinstance(group, OptimizationGroup)

    def test_all_groups_have_agent_codes(self):
        for name, group in OPTIMIZATION_GROUPS.items():
            assert len(group.agent_codes) > 0, f"Group '{name}' has no agent codes"

    def test_all_groups_have_prompt_names(self):
        for name, group in OPTIMIZATION_GROUPS.items():
            assert len(group.prompt_names) > 0, f"Group '{name}' has no prompt names"

    def test_all_agent_codes_covered(self):
        covered = set()
        for group in OPTIMIZATION_GROUPS.values():
            covered.update(group.agent_codes)
        assert covered == ALL_15_AGENTS

    def test_workflow_numbers_valid(self):
        for name, group in OPTIMIZATION_GROUPS.items():
            assert group.workflow in {
                1,
                2,
                3,
            }, f"Group '{name}' has invalid workflow: {group.workflow}"

    def test_group_immutability(self):
        group = get_group("wf3-creative-pipeline")
        with pytest.raises(FrozenInstanceError):
            group.name = "modified"

    def test_prompt_names_follow_naming_convention(self):
        pattern = re.compile(r"^zorven-wf\d+-\w+-\w+$")
        for name, group in OPTIMIZATION_GROUPS.items():
            for pn in group.prompt_names:
                assert pattern.match(pn), (
                    f"Prompt name '{pn}' in group '{name}' "
                    f"doesn't match zorven-wfN-agent-skill pattern"
                )
