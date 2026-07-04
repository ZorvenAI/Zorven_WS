"""Tests for prompt naming convention validator (§3.1)."""

import re

import pytest

from app.logic.prompt_naming import (
    ALL_AGENT_CODES,
    EXPECTED_FORMAT,
    VALID_AGENT_CODES,
    PromptNameParts,
    validate_prompt_name,
)


class TestValidNames:
    """Test valid prompt names are accepted."""

    def test_standard_wf1_prompt(self):
        parts = validate_prompt_name("zorven-wf1-mra-landscape")
        assert parts.workflow == 1
        assert parts.agent_code == "mra"
        assert parts.skill == "landscape"
        assert parts.variant is None

    def test_standard_wf2_prompt(self):
        parts = validate_prompt_name("zorven-wf2-bpa-positioning")
        assert parts.workflow == 2
        assert parts.agent_code == "bpa"
        assert parts.skill == "positioning"

    def test_standard_wf3_prompt(self):
        parts = validate_prompt_name("zorven-wf3-cga-creative")
        assert parts.workflow == 3
        assert parts.agent_code == "cga"

    def test_variant_suffix(self):
        """AC-2: Variant suffix supported."""
        parts = validate_prompt_name("zorven-wf3-cga-creative-v2")
        assert parts.variant == "v2"
        assert parts.full_name == "zorven-wf3-cga-creative-v2"
        assert parts.base_name == "zorven-wf3-cga-creative"

    def test_variant_with_numbers(self):
        parts = validate_prompt_name("zorven-wf1-mra-landscape-v3")
        assert parts.variant == "v3"

    def test_system_prompt(self):
        """AC-3: System prompts use zorven-wf<n>-<agent_code>-system."""
        parts = validate_prompt_name("zorven-wf1-mra-system")
        assert parts.skill == "system"
        assert parts.is_system is True
        assert parts.is_planner is False

    def test_planner_prompt(self):
        """AC-4: Planner prompts use zorven-wf<n>-<agent_code>-planner."""
        parts = validate_prompt_name("zorven-wf1-mra-planner")
        assert parts.skill == "planner"
        assert parts.is_planner is True
        assert parts.is_system is False

    def test_system_prompt_wf2(self):
        parts = validate_prompt_name("zorven-wf2-bpv-system")
        assert parts.is_system is True

    def test_planner_prompt_wf3(self):
        parts = validate_prompt_name("zorven-wf3-coa-planner")
        assert parts.is_planner is True

    def test_skill_with_underscore(self):
        parts = validate_prompt_name("zorven-wf1-mra-market_sizing")
        assert parts.skill == "market_sizing"

    def test_adpub_agent_code(self):
        """Multi-char agent code (4 chars)."""
        parts = validate_prompt_name("zorven-wf3-adpub-publish")
        assert parts.agent_code == "adpub"

    def test_tcia_agent_code(self):
        """4-char agent code."""
        parts = validate_prompt_name("zorven-wf1-tcia-trends")
        assert parts.agent_code == "tcia"

    def test_voca_agent_code(self):
        parts = validate_prompt_name("zorven-wf1-voca-sentiment")
        assert parts.agent_code == "voca"


class TestAllAgentCodes:
    """Verify all 15 agent codes are accepted in their correct workflow."""

    @pytest.mark.parametrize(
        "wf,code",
        [
            (1, "mra"),
            (1, "cia"),
            (1, "apa"),
            (1, "tcia"),
            (1, "voca"),
            (2, "bpa"),
            (2, "baa"),
            (2, "bpv"),
            (2, "nta"),
            (2, "bsa"),
            (3, "caa"),
            (3, "cga"),
            (3, "adpub"),
            (3, "coa"),
            (3, "ila"),
        ],
    )
    def test_agent_code_accepted(self, wf, code):
        name = f"zorven-wf{wf}-{code}-test"
        parts = validate_prompt_name(name)
        assert parts.agent_code == code
        assert parts.workflow == wf

    def test_all_15_codes_covered(self):
        assert len(ALL_AGENT_CODES) == 15


class TestInvalidNames:
    """Test invalid prompt names are rejected with corrective messages."""

    def test_empty_name(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_prompt_name("")

    def test_missing_prefix(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("wf1-mra-landscape")

    def test_wrong_workflow_number(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-wf4-mra-landscape")

    def test_workflow_zero(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-wf0-mra-landscape")

    def test_unknown_agent_code(self):
        with pytest.raises(ValueError, match="not valid for workflow"):
            validate_prompt_name("zorven-wf1-xyz-landscape")

    def test_agent_code_wrong_workflow(self):
        """WF2 agent code used with WF1 prefix."""
        with pytest.raises(ValueError, match="not valid for workflow 1"):
            validate_prompt_name("zorven-wf1-bpa-positioning")

    def test_uppercase_rejected(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-WF1-MRA-landscape")

    def test_missing_skill(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-wf1-mra")

    def test_trailing_hyphen(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-wf1-mra-")

    def test_special_characters(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-wf1-mra-land@scape")

    def test_spaces(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_name("zorven-wf1-mra-land scape")

    def test_corrective_message_includes_format(self):
        """AC-5: Error includes the expected format."""
        with pytest.raises(ValueError, match=re.escape(EXPECTED_FORMAT)):
            validate_prompt_name("bad-name")

    def test_corrective_message_includes_agent_codes(self):
        with pytest.raises(ValueError, match="agent codes"):
            validate_prompt_name("bad-name")


class TestPromptNameParts:
    """Test PromptNameParts dataclass."""

    def test_base_name(self):
        parts = PromptNameParts(workflow=1, agent_code="mra", skill="landscape")
        assert parts.base_name == "zorven-wf1-mra-landscape"

    def test_full_name_no_variant(self):
        parts = PromptNameParts(workflow=2, agent_code="bpa", skill="positioning")
        assert parts.full_name == "zorven-wf2-bpa-positioning"

    def test_full_name_with_variant(self):
        parts = PromptNameParts(
            workflow=3, agent_code="cga", skill="creative", variant="v2"
        )
        assert parts.full_name == "zorven-wf3-cga-creative-v2"

    def test_frozen(self):
        parts = PromptNameParts(workflow=1, agent_code="mra", skill="test")
        with pytest.raises(AttributeError):
            parts.workflow = 2  # type: ignore
