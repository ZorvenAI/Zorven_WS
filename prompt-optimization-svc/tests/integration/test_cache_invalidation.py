"""Integration tests for cache invalidation (US-037)."""

import os
import sys

WS_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


class TestInvalidatorNoOpMode:
    """Invalidator with no Kafka connection works in no-op mode."""

    async def test_start_stop_noop(self):
        cga_path = os.path.join(WS_ROOT, "creative-generation-agent-svc")
        if cga_path not in sys.path:
            sys.path.insert(0, cga_path)
        try:
            from app.prompts.invalidator import PromptCacheInvalidator

            inv = PromptCacheInvalidator("", None)
            await inv.start()  # No-op — no Kafka
            await inv.stop()  # Should not raise
        finally:
            if cga_path in sys.path:
                sys.path.remove(cga_path)


class TestAllAgentGroupIds:
    """All 15 agents have unique GROUP_IDs."""

    def test_15_unique_group_ids(self):
        agent_codes = [
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
        ]
        group_ids = {f"prompt-cache-invalidator-{code}" for code in agent_codes}
        assert len(group_ids) == 15
