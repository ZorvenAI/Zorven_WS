"""E2E tests for CRITICAL agent approval flow (US-060).

Exercises: requires_approval -> PENDING_APPROVAL -> approve/reject
-> canary deployment for adpub/coa agents.
"""

import uuid

import pytest

from app.logic.approval_gate import (
    CRITICAL_AGENTS,
    approve_run,
    reject_run,
    requires_approval,
)
from app.logic.candidate_validator import validate_candidate
from app.logic.lifecycle import PromptState
from app.logic.run_lifecycle import RunState


@pytest.mark.e2e
class TestApprovalGate:
    """CRITICAL agent approval flow (adpub/coa)."""

    def test_critical_agents_require_approval(self):
        """adpub/coa -> True, cga/mra -> False."""
        assert requires_approval("adpub") is True
        assert requires_approval("coa") is True
        assert requires_approval("ADPUB") is True  # Case-insensitive
        assert requires_approval("COA") is True

        assert requires_approval("cga") is False
        assert requires_approval("mra") is False
        assert requires_approval("bpa") is False
        assert requires_approval("") is False

    async def test_approve_run_transitions_to_canary(
        self, e2e_run_lifecycle, e2e_cache
    ):
        """PENDING_APPROVAL -> CANARY on approve."""
        run_id = str(uuid.uuid4())

        # Create run in PENDING_APPROVAL state
        await e2e_run_lifecycle.transition(
            run_id=run_id,
            from_state=RunState.QUEUED,
            to_state=RunState.ACQUIRING_LOCK,
            prompt_name="__e2e_approve",
            agent_code="adpub",
        )
        await e2e_run_lifecycle.transition(
            run_id=run_id,
            from_state=RunState.ACQUIRING_LOCK,
            to_state=RunState.LOADING_DATA,
            prompt_name="__e2e_approve",
            agent_code="adpub",
        )
        await e2e_run_lifecycle.transition(
            run_id=run_id,
            from_state=RunState.LOADING_DATA,
            to_state=RunState.OPTIMIZING,
            prompt_name="__e2e_approve",
            agent_code="adpub",
        )
        await e2e_run_lifecycle.transition(
            run_id=run_id,
            from_state=RunState.OPTIMIZING,
            to_state=RunState.VALIDATING,
            prompt_name="__e2e_approve",
            agent_code="adpub",
        )
        await e2e_run_lifecycle.transition(
            run_id=run_id,
            from_state=RunState.VALIDATING,
            to_state=RunState.PENDING_APPROVAL,
            prompt_name="__e2e_approve",
            agent_code="adpub",
        )

        # Approve
        decision = await approve_run(
            run_id=run_id,
            approved_by="admin@zorven.ai",
            lifecycle_manager=e2e_run_lifecycle,
            prompt_name="__e2e_approve",
            agent_code="adpub",
        )
        assert decision.decision == "approved"
        assert decision.approved_by == "admin@zorven.ai"

        # Verify state in Redis
        state = await e2e_run_lifecycle.get_run_state(run_id)
        assert state is not None
        assert state["state"] == "CANARY"

    async def test_reject_run_transitions_to_rejected(
        self, e2e_run_lifecycle, e2e_cache
    ):
        """PENDING_APPROVAL -> REJECTED with reason."""
        run_id = str(uuid.uuid4())

        # Walk to PENDING_APPROVAL
        for from_s, to_s in [
            (RunState.QUEUED, RunState.ACQUIRING_LOCK),
            (RunState.ACQUIRING_LOCK, RunState.LOADING_DATA),
            (RunState.LOADING_DATA, RunState.OPTIMIZING),
            (RunState.OPTIMIZING, RunState.VALIDATING),
            (RunState.VALIDATING, RunState.PENDING_APPROVAL),
        ]:
            await e2e_run_lifecycle.transition(
                run_id=run_id,
                from_state=from_s,
                to_state=to_s,
                prompt_name="__e2e_reject",
                agent_code="coa",
            )

        # Reject
        decision = await reject_run(
            run_id=run_id,
            approved_by="admin@zorven.ai",
            reason="Regression in cost efficiency scorer",
            lifecycle_manager=e2e_run_lifecycle,
            prompt_name="__e2e_reject",
            agent_code="coa",
        )
        assert decision.decision == "rejected"
        assert decision.reason == "Regression in cost efficiency scorer"

        state = await e2e_run_lifecycle.get_run_state(run_id)
        assert state["state"] == "REJECTED"

    def test_candidate_with_regression_gets_pending(self):
        """>5% aggregate but >3% individual regression -> PENDING_APPROVAL."""
        candidate_scores = {
            "json_compliance": 0.99,
            "brand_voice": 0.70,  # Regression from 0.75 (6.7% drop > 3%)
            "pii_safety": 0.99,
        }
        production_scores = {
            "json_compliance": 0.80,
            "brand_voice": 0.75,
            "pii_safety": 0.80,
        }

        result = validate_candidate(
            candidate_scores,
            production_scores,
            improvement_threshold=0.05,
            regression_threshold=0.03,
        )
        assert result.decision == "PENDING_APPROVAL"
        assert "brand_voice" in result.scorer_regressions

    async def test_full_critical_agent_pipeline(
        self,
        e2e_registry,
        e2e_lifecycle,
        e2e_run_lifecycle,
        e2e_canary,
        e2e_prompt_name,
    ):
        """Register adpub prompt, validate->PENDING, approve, start canary."""
        name = e2e_prompt_name("critical-flow")
        run_id = str(uuid.uuid4())

        # 1. Register prompt
        info = e2e_registry.register_prompt(
            name=name,
            template="Ad publishing template for {{context.brand_name}}.",
            tags={"state": "DRAFT", "agent_code": "adpub"},
        )

        # 2. Verify requires approval
        assert requires_approval("adpub") is True

        # 3. Walk run lifecycle to PENDING_APPROVAL
        for from_s, to_s in [
            (RunState.QUEUED, RunState.ACQUIRING_LOCK),
            (RunState.ACQUIRING_LOCK, RunState.LOADING_DATA),
            (RunState.LOADING_DATA, RunState.OPTIMIZING),
            (RunState.OPTIMIZING, RunState.VALIDATING),
            (RunState.VALIDATING, RunState.PENDING_APPROVAL),
        ]:
            await e2e_run_lifecycle.transition(
                run_id=run_id,
                from_state=from_s,
                to_state=to_s,
                prompt_name=name,
                agent_code="adpub",
            )

        # 4. Approve
        decision = await approve_run(
            run_id=run_id,
            approved_by="admin",
            lifecycle_manager=e2e_run_lifecycle,
            prompt_name=name,
            agent_code="adpub",
        )
        assert decision.decision == "approved"

        # 5. Transition prompt to CANARY in MLflow
        e2e_lifecycle.transition(
            name, info.version, PromptState.DRAFT, PromptState.STAGING
        )
        e2e_lifecycle.transition(
            name, info.version, PromptState.STAGING, PromptState.CANARY
        )

        # 6. Start canary deployment
        canary_state = await e2e_canary.start_canary(
            prompt_name=name,
            canary_version=info.version,
            production_version=0,
            agent_code="adpub",
        )
        assert canary_state.active is True
        assert canary_state.agent_code == "adpub"
