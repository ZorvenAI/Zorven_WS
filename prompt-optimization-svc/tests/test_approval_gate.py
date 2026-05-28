"""Unit tests for approval gate (US-034, OPT-05)."""

from datetime import datetime, timezone

from app.logic.approval_gate import (
    CRITICAL_AGENTS,
    ApprovalDecision,
    requires_approval,
)
from app.registries.prompt_catalog import AGENT_PORTS


class TestRequiresApproval:
    """AC-1: Auto-promotion disabled for ADPUB and COA."""

    def test_adpub_requires_approval(self):
        assert requires_approval("adpub") is True

    def test_coa_requires_approval(self):
        assert requires_approval("coa") is True

    def test_mra_does_not_require(self):
        assert requires_approval("mra") is False

    def test_cga_does_not_require(self):
        assert requires_approval("cga") is False

    def test_bpa_does_not_require(self):
        assert requires_approval("bpa") is False

    def test_ila_does_not_require(self):
        assert requires_approval("ila") is False

    def test_only_adpub_and_coa_critical(self):
        for agent in AGENT_PORTS:
            expected = agent in ("adpub", "coa")
            assert (
                requires_approval(agent) is expected
            ), f"Agent {agent}: expected {expected}"

    def test_case_insensitive(self):
        assert requires_approval("ADPUB") is True
        assert requires_approval("COA") is True
        assert requires_approval("Adpub") is True

    def test_empty_agent_code(self):
        assert requires_approval("") is False


class TestCriticalAgents:
    def test_exactly_two_entries(self):
        assert len(CRITICAL_AGENTS) == 2

    def test_contains_adpub_and_coa(self):
        assert "adpub" in CRITICAL_AGENTS
        assert "coa" in CRITICAL_AGENTS

    def test_is_tuple(self):
        assert isinstance(CRITICAL_AGENTS, tuple)


class TestApprovalDecision:
    def test_approved_decision(self):
        d = ApprovalDecision(
            run_id="run-123",
            agent_code="coa",
            prompt_name="zorven-wf3-coa-system",
            decision="approved",
            approved_by="admin@company.com",
        )
        assert d.decision == "approved"
        assert d.approved_by == "admin@company.com"
        assert isinstance(d.decided_at, datetime)

    def test_rejected_decision(self):
        d = ApprovalDecision(
            run_id="run-456",
            agent_code="adpub",
            prompt_name="zorven-wf3-adpub-publishing",
            decision="rejected",
            approved_by="owner@company.com",
            reason="Performance concerns",
        )
        assert d.decision == "rejected"
        assert d.reason == "Performance concerns"

    def test_decided_at_auto_populated(self):
        d = ApprovalDecision(
            run_id="r",
            agent_code="coa",
            prompt_name="p",
            decision="approved",
            approved_by="admin",
        )
        assert isinstance(d.decided_at, datetime)
        assert d.decided_at.tzinfo is not None

    def test_default_reason_empty(self):
        d = ApprovalDecision(
            run_id="r",
            agent_code="coa",
            prompt_name="p",
            decision="approved",
            approved_by="admin",
        )
        assert d.reason == ""
