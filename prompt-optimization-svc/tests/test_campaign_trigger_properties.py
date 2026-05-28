"""Hypothesis property tests for campaign trigger (US-038)."""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.kafka.campaign_trigger import CampaignCompletionTrigger, WF3_AGENTS
from app.logic.debounce import DEBOUNCE_KEY_TEMPLATE


class TestDebounceKeyProperties:
    @given(st.text(min_size=1, max_size=30), st.text(min_size=1, max_size=10))
    @settings(max_examples=50, deadline=None)
    def test_key_always_non_empty(self, tenant_id, agent_code):
        key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id=tenant_id, agent_code=agent_code)
        assert len(key) > 0
        assert "reopt:debounce:" in key


class TestHandleEventProperties:
    @given(
        st.dictionaries(
            st.text(max_size=20),
            st.text(max_size=50),
            max_size=5,
        )
    )
    @settings(max_examples=50, deadline=None)
    async def test_any_dict_handled(self, event):
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event(event)


class TestWf3AgentSetProperties:
    @given(st.sampled_from(sorted(WF3_AGENTS)))
    @settings(max_examples=5, deadline=None)
    def test_all_wf3_agents_valid(self, agent):
        assert agent in {"caa", "cga", "adpub", "coa", "ila"}
