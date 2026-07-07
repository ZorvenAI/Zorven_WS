"""Hypothesis property tests for cache invalidation (US-037)."""

import os

from hypothesis import given, settings
from hypothesis import strategies as st

AGENT_SERVICES = {
    "market-research-agent-svc": "mra",
    "competitor-intel-agent-svc": "cia",
    "audience-persona-agent-svc": "apa",
    "trend-cultural-agent-svc": "tcia",
    "voc-agent-svc": "voca",
    "brand-positioning-agent-svc": "bpa",
    "brand-architecture-agent-svc": "baa",
    "brand-personality-agent-svc": "bpv",
    "brand-naming-agent-svc": "nta",
    "brand-story-agent-svc": "bsa",
    "campaign-architecture-agent-svc": "caa",
    "creative-generation-agent-svc": "cga",
    "ad-publishing-agent-svc": "adpub",
    "campaign-optimization-agent-svc": "coa",
    "intelligence-loop-agent-svc": "ila",
}

WS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestInvalidatorFileProperties:
    @given(st.sampled_from(sorted(AGENT_SERVICES.keys())))
    @settings(max_examples=15, deadline=None)
    def test_every_agent_has_invalidator(self, svc_dir):
        path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
        assert os.path.isfile(path)

    @given(st.sampled_from(sorted(AGENT_SERVICES.keys())))
    @settings(max_examples=15, deadline=None)
    def test_every_invalidator_has_class(self, svc_dir):
        path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
        with open(path) as f:
            content = f.read()
        assert "class PromptCacheInvalidator" in content

    @given(st.sampled_from(sorted(AGENT_SERVICES.items())))
    @settings(max_examples=15, deadline=None)
    def test_every_group_id_contains_agent_code(self, svc_agent):
        svc_dir, agent_code = svc_agent
        path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
        with open(path) as f:
            content = f.read()
        assert f"prompt-cache-invalidator-{agent_code}" in content
