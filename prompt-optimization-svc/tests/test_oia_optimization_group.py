"""Unit tests for OIA optimization group registration (L-03).

Tests AC-1: group registered, AC-3: re-seeding idempotent.
"""

from dataclasses import FrozenInstanceError

import pytest

from app.registries.optimization_groups import (
    OPTIMIZATION_GROUPS,
    get_group,
)


class TestOiaOptimizationGroup:
    def test_oia_group_registered(self):
        assert "oia-onboarding-pipeline" in OPTIMIZATION_GROUPS

    def test_oia_group_has_nine_prompts(self):
        group = get_group("oia-onboarding-pipeline")
        assert len(group.prompt_names) == 9

    def test_oia_group_prompt_names(self):
        group = get_group("oia-onboarding-pipeline")
        expected = {
            "zorven-oia-research-brief",
            "zorven-oia-questionnaire",
            "zorven-oia-analyze-stream",
            "zorven-oia-sufficiency",
            "zorven-oia-followups",
            "zorven-oia-media-analysis",
            "zorven-oia-media-analysis-multi",
            "zorven-oia-summarize-recording",
            "zorven-oia-extract-fields",
        }
        assert set(group.prompt_names) == expected

    def test_oia_group_agent_code(self):
        group = get_group("oia-onboarding-pipeline")
        assert group.agent_codes == ("oia",)

    def test_oia_group_workflow_zero(self):
        group = get_group("oia-onboarding-pipeline")
        assert group.workflow == 0

    def test_oia_group_has_description(self):
        group = get_group("oia-onboarding-pipeline")
        assert len(group.description) > 0

    def test_oia_group_is_frozen(self):
        group = get_group("oia-onboarding-pipeline")
        with pytest.raises(FrozenInstanceError):
            group.name = "modified"

    def test_seed_idempotent(self):
        """Re-reading the group dict returns the same entries."""
        group1 = get_group("oia-onboarding-pipeline")
        group2 = get_group("oia-onboarding-pipeline")
        assert group1 is group2
