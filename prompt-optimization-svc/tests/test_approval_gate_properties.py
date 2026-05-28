"""Hypothesis property tests for approval gate (US-034)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.logic.approval_gate import requires_approval
from app.registries.prompt_catalog import AGENT_PORTS


class TestRequiresApprovalProperties:
    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_deterministic(self, agent_code):
        r1 = requires_approval(agent_code)
        r2 = requires_approval(agent_code)
        assert r1 == r2

    @given(st.sampled_from(sorted(AGENT_PORTS.keys())))
    @settings(max_examples=15, deadline=None)
    def test_only_adpub_coa_from_agents(self, agent):
        result = requires_approval(agent)
        expected = agent in ("adpub", "coa")
        assert result is expected

    @given(st.text(max_size=50))
    @settings(max_examples=50, deadline=None)
    def test_never_raises(self, agent_code):
        result = requires_approval(agent_code)
        assert isinstance(result, bool)

    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_returns_bool(self, agent_code):
        assert isinstance(requires_approval(agent_code), bool)
