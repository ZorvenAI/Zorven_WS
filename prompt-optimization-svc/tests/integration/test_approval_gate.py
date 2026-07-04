"""Integration tests for approval gate (US-034).

Requires real Redis for state transitions.
"""

from .conftest import REDIS_URL, requires_redis


@requires_redis
class TestApprovalWithRedis:
    """Approval/rejection with real Redis state."""

    async def test_approve_transitions_state(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.approval_gate import approve_run
        from app.logic.run_lifecycle import RunLifecycleManager, RunState

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = RunLifecycleManager(prompt_cache=cache)

            # Set up: transition to PENDING_APPROVAL
            run_id = "__test_approve_run"
            await mgr.transition(run_id, RunState.QUEUED, RunState.ACQUIRING_LOCK)
            await mgr.transition(run_id, RunState.ACQUIRING_LOCK, RunState.LOADING_DATA)
            await mgr.transition(run_id, RunState.LOADING_DATA, RunState.OPTIMIZING)
            await mgr.transition(run_id, RunState.OPTIMIZING, RunState.VALIDATING)
            await mgr.transition(run_id, RunState.VALIDATING, RunState.PENDING_APPROVAL)

            # Approve
            decision = await approve_run(
                run_id=run_id,
                approved_by="admin@test.com",
                lifecycle_manager=mgr,
                prompt_name="test-prompt",
                agent_code="coa",
            )
            assert decision.decision == "approved"

            # Verify state
            state = await mgr.get_run_state(run_id)
            assert state["state"] == "CANARY"
        finally:
            # Cleanup
            for pattern in ("prompt:optimization:progress:__test*",):
                async for key in real_redis.scan_iter(match=pattern):
                    await real_redis.delete(key)
            await cache.close()

    async def test_reject_transitions_state(self, real_redis):
        from app.cache.prompt_cache import PromptCacheManager
        from app.logic.approval_gate import reject_run
        from app.logic.run_lifecycle import RunLifecycleManager, RunState

        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        try:
            mgr = RunLifecycleManager(prompt_cache=cache)

            run_id = "__test_reject_run"
            await mgr.transition(run_id, RunState.QUEUED, RunState.ACQUIRING_LOCK)
            await mgr.transition(run_id, RunState.ACQUIRING_LOCK, RunState.LOADING_DATA)
            await mgr.transition(run_id, RunState.LOADING_DATA, RunState.OPTIMIZING)
            await mgr.transition(run_id, RunState.OPTIMIZING, RunState.VALIDATING)
            await mgr.transition(run_id, RunState.VALIDATING, RunState.PENDING_APPROVAL)

            decision = await reject_run(
                run_id=run_id,
                approved_by="owner@test.com",
                reason="Insufficient testing",
                lifecycle_manager=mgr,
                prompt_name="test-prompt",
                agent_code="adpub",
            )
            assert decision.decision == "rejected"
            assert decision.reason == "Insufficient testing"

            state = await mgr.get_run_state(run_id)
            assert state["state"] == "REJECTED"
        finally:
            for pattern in ("prompt:optimization:progress:__test*",):
                async for key in real_redis.scan_iter(match=pattern):
                    await real_redis.delete(key)
            await cache.close()
