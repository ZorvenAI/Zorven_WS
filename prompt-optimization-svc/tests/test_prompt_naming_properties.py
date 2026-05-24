"""Hypothesis property tests for prompt naming convention (US-006)."""

from hypothesis import given, settings as hyp_settings, assume
from hypothesis import strategies as st

from app.logic.prompt_naming import (
    ALL_AGENT_CODES,
    VALID_AGENT_CODES,
    PromptNameParts,
    validate_prompt_name,
)

_wf = st.sampled_from([1, 2, 3])
_agent = st.sampled_from(sorted(ALL_AGENT_CODES))
_skill = st.from_regex(r"[a-z][a-z0-9_]{0,20}", fullmatch=True)
_variant = st.one_of(st.none(), st.from_regex(r"[a-z0-9][a-z0-9_]{0,10}", fullmatch=True))


class TestValidNameProperties:

    @given(wf=_wf, skill=_skill, variant=_variant)
    @hyp_settings(max_examples=50)
    def test_valid_names_always_parse(self, wf, skill, variant):
        codes = sorted(VALID_AGENT_CODES[wf])
        agent = codes[0]
        name = f"zorven-wf{wf}-{agent}-{skill}"
        if variant:
            name += f"-{variant}"
        parts = validate_prompt_name(name)
        assert parts.workflow == wf
        assert parts.agent_code == agent

    @given(wf=_wf, skill=_skill)
    @hyp_settings(max_examples=30)
    def test_round_trip_base_name(self, wf, skill):
        agent = sorted(VALID_AGENT_CODES[wf])[0]
        name = f"zorven-wf{wf}-{agent}-{skill}"
        parts = validate_prompt_name(name)
        assert parts.base_name == name

    @given(wf=_wf, skill=_skill, variant=st.from_regex(r"[a-z0-9]{1,5}", fullmatch=True))
    @hyp_settings(max_examples=30)
    def test_round_trip_full_name(self, wf, skill, variant):
        agent = sorted(VALID_AGENT_CODES[wf])[0]
        name = f"zorven-wf{wf}-{agent}-{skill}-{variant}"
        parts = validate_prompt_name(name)
        assert parts.full_name == name

    @given(name=st.text(min_size=0, max_size=100))
    @hyp_settings(max_examples=100)
    def test_invalid_names_raise_or_parse(self, name):
        """Any string either parses successfully or raises ValueError."""
        try:
            parts = validate_prompt_name(name)
            assert isinstance(parts, PromptNameParts)
        except ValueError:
            pass  # Expected for invalid names


class TestPromptNamePartsProperties:

    @given(wf=_wf, skill=_skill)
    @hyp_settings(max_examples=20)
    def test_base_name_always_starts_with_zorven(self, wf, skill):
        agent = sorted(VALID_AGENT_CODES[wf])[0]
        parts = PromptNameParts(workflow=wf, agent_code=agent, skill=skill)
        assert parts.base_name.startswith("zorven-wf")

    @given(wf=_wf, skill=_skill)
    @hyp_settings(max_examples=20)
    def test_system_and_planner_flags(self, wf, skill):
        agent = sorted(VALID_AGENT_CODES[wf])[0]
        parts = PromptNameParts(workflow=wf, agent_code=agent, skill=skill)
        assert parts.is_system == (skill == "system")
        assert parts.is_planner == (skill == "planner")
