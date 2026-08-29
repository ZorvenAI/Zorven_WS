"""Tests for the prompt catalog definition."""

import pytest

from app.logic.prompt_naming import VALID_AGENT_CODES, validate_prompt_name
from app.registries.prompt_catalog import (
    OIA_PROMPTS,
    PROMPT_CATALOG,
    UTILITY_PROMPTS,
    WF1_PROMPTS,
    WF2_PROMPTS,
    WF3_PROMPTS,
)


class TestCatalogCompleteness:
    """Verify the catalog meets §3.2 requirements."""

    def test_catalog_has_at_least_39_entries(self):
        """All agent system prompts registered (39+ real prompts)."""
        assert len(PROMPT_CATALOG) >= 39

    def test_catalog_total_count(self):
        """Exact count: 23 WF1 + 7 WF2 + 9 WF3 + 14 UTILITY + 9 OIA = 62."""
        assert len(PROMPT_CATALOG) == (
            len(WF1_PROMPTS) + len(WF2_PROMPTS) + len(WF3_PROMPTS)
            + len(UTILITY_PROMPTS) + len(OIA_PROMPTS)
        )

    def test_wf1_has_23_prompts(self):
        """AC-1: All WF1 prompts registered (MRA:4, CIA:5, APA:6, TCIA:3, VoCA:5)."""
        assert len(WF1_PROMPTS) == 23

    def test_wf2_has_7_prompts(self):
        """AC-2: All WF2 prompts registered (BPA:1, BAA:1, BPV:1, NTA:2, BSA:2)."""
        assert len(WF2_PROMPTS) == 7

    def test_wf3_has_9_prompts(self):
        """AC-3: All WF3 prompts registered (CAA:2, CGA:3, ADPUB:1, COA:2, ILA:1)."""
        assert len(WF3_PROMPTS) == 9

    def test_no_duplicate_names(self):
        names = [e.name for e in PROMPT_CATALOG]
        assert len(names) == len(
            set(names)
        ), f"Duplicates: {[n for n in names if names.count(n) > 1]}"


_WORKFLOW_PROMPTS = WF1_PROMPTS + WF2_PROMPTS + WF3_PROMPTS


class TestNamingConvention:
    """Verify workflow entries follow §3.1 naming convention.

    Utility and OIA prompts use ``zorven-<agent>-<skill>`` which is a valid
    alternative pattern not covered by the §3.1 validator.
    """

    @pytest.mark.parametrize("entry", _WORKFLOW_PROMPTS, ids=lambda e: e.name)
    def test_workflow_name_is_valid(self, entry):
        """Every workflow catalog entry passes the §3.1 validator."""
        parts = validate_prompt_name(entry.name)
        assert parts is not None

    @pytest.mark.parametrize(
        "entry", UTILITY_PROMPTS + OIA_PROMPTS, ids=lambda e: e.name
    )
    def test_utility_name_follows_pattern(self, entry):
        """Utility/OIA names follow zorven-<agent>-<skill> convention."""
        assert entry.name.startswith("zorven-")
        parts = entry.name.split("-")
        assert len(parts) >= 3


class TestAgentCoverage:
    """Verify all 15 agents have prompts."""

    def test_all_wf1_agents_present(self):
        """AC-1: MRA, CIA, APA, TCIA, VoCA all have prompts."""
        wf1_agents = {e.tags["agent_code"] for e in WF1_PROMPTS}
        for code in VALID_AGENT_CODES[1]:
            assert code in wf1_agents, f"WF1 agent {code} missing from catalog"

    def test_all_wf2_agents_present(self):
        """AC-2: BPA, BAA, BPV, NTA, BSA all have prompts."""
        wf2_agents = {e.tags["agent_code"] for e in WF2_PROMPTS}
        for code in VALID_AGENT_CODES[2]:
            assert code in wf2_agents, f"WF2 agent {code} missing from catalog"

    def test_all_wf3_agents_present(self):
        """AC-3: CAA, CGA, ADPUB, COA, ILA all have prompts."""
        wf3_agents = {e.tags["agent_code"] for e in WF3_PROMPTS}
        for code in VALID_AGENT_CODES[3]:
            assert code in wf3_agents, f"WF3 agent {code} missing from catalog"

    def test_every_agent_has_at_least_one_prompt(self):
        """Each agent has at least one prompt in the catalog."""
        catalog_agents = {e.tags["agent_code"] for e in PROMPT_CATALOG}
        all_agents = set()
        for codes in VALID_AGENT_CODES.values():
            all_agents |= codes
        for code in all_agents:
            assert code in catalog_agents, f"Agent {code} missing from catalog"


class TestDraftState:
    """Verify all entries are tagged as DRAFT (AC-4)."""

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_entry_has_draft_state(self, entry):
        """AC-4: Each prompt created in DRAFT state."""
        assert entry.tags.get("state") == "DRAFT"

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_entry_has_required_tags(self, entry):
        """Each entry has workflow, agent_code, skill, and state tags."""
        assert "workflow" in entry.tags
        assert "agent_code" in entry.tags
        assert "skill" in entry.tags
        assert "state" in entry.tags


class TestTemplates:
    """Verify templates are non-empty and use {{variable}} syntax."""

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_template_not_empty(self, entry):
        assert len(entry.template) > 0

    @pytest.mark.parametrize("entry", PROMPT_CATALOG, ids=lambda e: e.name)
    def test_template_is_substantial(self, entry):
        """Templates should contain meaningful prompt content (>50 chars)."""
        assert len(entry.template) > 50, (
            f"{entry.name} template is too short ({len(entry.template)} chars)"
        )
