"""Unit tests for cache invalidation across all 15 agents (US-037)."""

import os

# All 15 agent service directories and their agent codes
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


class TestAllAgentsHaveInvalidators:
    """AC-1: All 15 agents have cache invalidation consumers."""

    def test_all_15_have_invalidator_file(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            assert os.path.isfile(path), f"Missing invalidator: {svc_dir}"

    def test_all_15_agents_covered(self):
        assert len(AGENT_SERVICES) == 15


class TestGroupIdUniqueness:
    def test_all_group_ids_unique(self):
        group_ids = set()
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            for line in content.split("\n"):
                if "GROUP_ID" in line and "=" in line:
                    group_id = line.split("=")[1].strip().strip('"').strip("'")
                    assert (
                        group_id not in group_ids
                    ), f"Duplicate GROUP_ID '{group_id}' in {svc_dir}"
                    group_ids.add(group_id)
                    break
        assert len(group_ids) == 15


class TestInvalidatorGroupIdFormat:
    def test_group_ids_follow_convention(self):
        for svc_dir, agent_code in AGENT_SERVICES.items():
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            expected = f"prompt-cache-invalidator-{agent_code}"
            assert expected in content, f"{svc_dir}: expected GROUP_ID '{expected}'"


class TestInvalidatorFileContent:
    def test_all_have_class(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            assert "class PromptCacheInvalidator" in content

    def test_all_subscribe_to_topic(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            assert "prompt-lifecycle-events" in content

    def test_all_handle_prompt_promoted(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            assert "prompt.promoted" in content

    def test_all_have_start_stop(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            assert "async def start" in content
            assert "async def stop" in content

    def test_all_have_handle_event(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "prompts", "invalidator.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            assert "async def handle_event" in content


class TestMainPyWiring:
    def test_all_main_py_reference_invalidator(self):
        for svc_dir in AGENT_SERVICES:
            path = os.path.join(WS_ROOT, svc_dir, "app", "main.py")
            if not os.path.isfile(path):
                continue
            with open(path) as f:
                content = f.read()
            assert (
                "PromptCacheInvalidator" in content
            ), f"{svc_dir}: main.py does not import PromptCacheInvalidator"
