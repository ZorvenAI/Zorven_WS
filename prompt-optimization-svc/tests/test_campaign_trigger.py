"""Unit tests for campaign completion trigger (US-038)."""

from app.kafka.campaign_trigger import (
    GROUP_ID,
    TOPIC,
    WF3_AGENTS,
    CampaignCompletionTrigger,
)
from app.logic.debounce import (
    DEBOUNCE_KEY_TEMPLATE,
    DEBOUNCE_TTL_SECONDS,
)


class TestDebounceConstants:
    """AC-1: 24h debounce window."""

    def test_debounce_ttl_24h(self):
        assert DEBOUNCE_TTL_SECONDS == 24 * 3600

    def test_debounce_key_format(self):
        key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id="t1", agent_code="cga")
        assert key == "reopt:debounce:t1:cga"

    def test_debounce_key_includes_both_ids(self):
        key = DEBOUNCE_KEY_TEMPLATE.format(tenant_id="abc", agent_code="coa")
        assert "abc" in key
        assert "coa" in key


class TestWf3Agents:
    def test_wf3_agents_set(self):
        assert WF3_AGENTS == {"caa", "cga", "adpub", "coa", "ila"}

    def test_wf3_agents_count(self):
        assert len(WF3_AGENTS) == 5

    def test_wf1_agents_not_in_wf3(self):
        for agent in ("mra", "cia", "apa", "tcia", "voca"):
            assert agent not in WF3_AGENTS

    def test_wf2_agents_not_in_wf3(self):
        for agent in ("bpa", "baa", "bpv", "nta", "bsa"):
            assert agent not in WF3_AGENTS


class TestTriggerConstants:
    def test_topic(self):
        assert TOPIC == "agent.optimization.action_executed"

    def test_group_id(self):
        assert GROUP_ID == "prompt-reoptimization-trigger"

    def test_quality_threshold(self):
        from app.core.config import settings

        assert settings.REOPT_QUALITY_THRESHOLD == 0.7

    def test_debounce_hours(self):
        from app.core.config import settings

        assert settings.REOPT_DEBOUNCE_HOURS == 24


class TestHandleEvent:
    """Event handling logic."""

    async def test_wf3_agent_accepted(self):
        trigger = CampaignCompletionTrigger("", None)
        # Should not raise for WF3 agents
        await trigger.handle_event(
            {
                "tenant_id": "t1",
                "agent_code": "cga",
                "prompt_name": "zorven-wf3-cga-system",
                "quality_score": 0.5,
            }
        )

    async def test_wf1_agent_skipped(self):
        """AC-3: Non-WF3 agents skipped with reason."""
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event(
            {
                "tenant_id": "t1",
                "agent_code": "mra",
                "prompt_name": "zorven-wf1-mra-system",
                "quality_score": 0.5,
            }
        )

    async def test_wf2_agent_skipped(self):
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event(
            {
                "tenant_id": "t1",
                "agent_code": "bpa",
                "quality_score": 0.5,
            }
        )

    async def test_empty_event_skipped(self):
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event({})

    async def test_missing_tenant_id_skipped(self):
        """AC-3: Missing tenant_id skipped."""
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event(
            {
                "agent_code": "cga",
                "quality_score": 0.5,
            }
        )

    async def test_above_threshold_skipped(self):
        """AC-2: Quality >= threshold → skip."""
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event(
            {
                "tenant_id": "t1",
                "agent_code": "cga",
                "quality_score": 0.9,
            }
        )

    async def test_empty_agent_code_skipped(self):
        trigger = CampaignCompletionTrigger("", None)
        await trigger.handle_event(
            {
                "tenant_id": "t1",
                "agent_code": "",
                "quality_score": 0.3,
            }
        )


class TestTriggerLifecycle:
    async def test_start_stop_noop(self):
        trigger = CampaignCompletionTrigger("", None)
        await trigger.start()
        await trigger.stop()
