"""Unit tests for optimization run lifecycle (US-020)."""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.logic.run_lifecycle import (
    ACTIVE_STATES,
    DEFERRED_RETRY_SECONDS,
    InvalidRunTransitionError,
    RUN_EVENT_MAP,
    RunLifecycleManager,
    RunState,
    TERMINAL_STATES,
    VALID_RUN_TRANSITIONS,
)
from .conftest import REDIS_URL, requires_redis


class TestRunStateEnum:
    def test_has_13_states(self):
        assert len(RunState) == 13

    def test_main_sequence(self):
        main = [
            RunState.QUEUED, RunState.ACQUIRING_LOCK,
            RunState.LOADING_DATA, RunState.OPTIMIZING,
            RunState.VALIDATING, RunState.CANARY,
            RunState.PROMOTING, RunState.COMPLETED,
        ]
        assert len(main) == 8

    def test_side_states(self):
        side = [
            RunState.DEFERRED, RunState.PENDING_APPROVAL,
            RunState.REJECTED, RunState.ROLLED_BACK, RunState.FAILED,
        ]
        assert len(side) == 5

    def test_terminal_states(self):
        assert RunState.COMPLETED in TERMINAL_STATES
        assert RunState.FAILED in TERMINAL_STATES
        assert RunState.REJECTED in TERMINAL_STATES
        assert RunState.ROLLED_BACK in TERMINAL_STATES

    def test_active_states_excludes_terminal(self):
        for s in TERMINAL_STATES:
            assert s not in ACTIVE_STATES

    def test_every_state_has_event(self):
        for state in RunState:
            assert state in RUN_EVENT_MAP


class TestValidTransitions:
    def test_queued_to_acquiring_lock(self):
        mgr = RunLifecycleManager()
        assert mgr.validate_transition(
            RunState.QUEUED, RunState.ACQUIRING_LOCK
        )

    def test_acquiring_lock_to_loading_data(self):
        mgr = RunLifecycleManager()
        assert mgr.validate_transition(
            RunState.ACQUIRING_LOCK, RunState.LOADING_DATA
        )

    def test_acquiring_lock_to_deferred(self):
        """AC-2: Lock conflict → DEFERRED."""
        mgr = RunLifecycleManager()
        assert mgr.validate_transition(
            RunState.ACQUIRING_LOCK, RunState.DEFERRED
        )

    def test_deferred_to_queued(self):
        """DEFERRED can retry by going back to QUEUED."""
        mgr = RunLifecycleManager()
        assert mgr.validate_transition(
            RunState.DEFERRED, RunState.QUEUED
        )

    def test_validating_to_pending_approval(self):
        mgr = RunLifecycleManager()
        assert mgr.validate_transition(
            RunState.VALIDATING, RunState.PENDING_APPROVAL
        )

    def test_full_happy_path(self):
        mgr = RunLifecycleManager()
        path = [
            (RunState.QUEUED, RunState.ACQUIRING_LOCK),
            (RunState.ACQUIRING_LOCK, RunState.LOADING_DATA),
            (RunState.LOADING_DATA, RunState.OPTIMIZING),
            (RunState.OPTIMIZING, RunState.VALIDATING),
            (RunState.VALIDATING, RunState.CANARY),
            (RunState.CANARY, RunState.PROMOTING),
            (RunState.PROMOTING, RunState.COMPLETED),
        ]
        for from_s, to_s in path:
            assert mgr.validate_transition(from_s, to_s)


class TestInvalidTransitions:
    def test_queued_to_completed(self):
        mgr = RunLifecycleManager()
        with pytest.raises(InvalidRunTransitionError):
            mgr.validate_transition(RunState.QUEUED, RunState.COMPLETED)

    def test_completed_to_anything(self):
        mgr = RunLifecycleManager()
        with pytest.raises(InvalidRunTransitionError):
            mgr.validate_transition(RunState.COMPLETED, RunState.QUEUED)

    def test_failed_is_terminal(self):
        mgr = RunLifecycleManager()
        with pytest.raises(InvalidRunTransitionError):
            mgr.validate_transition(RunState.FAILED, RunState.QUEUED)

    def test_error_includes_allowed_states(self):
        try:
            RunLifecycleManager().validate_transition(
                RunState.QUEUED, RunState.COMPLETED
            )
        except InvalidRunTransitionError as e:
            assert "ACQUIRING_LOCK" in str(e)


class TestDeferredRetry:
    def test_deferred_retry_is_1_hour(self):
        assert DEFERRED_RETRY_SECONDS == 3600


@requires_redis
class TestRunLifecycleWithRedis:
    """AC-1: State persisted to Redis progress hash."""

    @pytest.fixture
    async def manager(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        mgr = RunLifecycleManager(prompt_cache=cache)
        yield mgr
        r = await cache.connect()
        async for key in r.scan_iter(
            match="prompt:optimization:progress:__test*"
        ):
            await r.delete(key)
        await cache.close()

    async def test_transition_persists_to_redis(self, manager):
        await manager.transition(
            "__test-run-1",
            RunState.QUEUED,
            RunState.ACQUIRING_LOCK,
            prompt_name="zorven-wf1-mra-system",
            agent_code="mra",
        )
        state = await manager.get_run_state("__test-run-1")
        assert state is not None
        assert state["state"] == "ACQUIRING_LOCK"

    async def test_defer_persists_retry_time(self, manager):
        retry_at = await manager.defer_on_lock_conflict(
            "__test-run-defer",
            prompt_name="test",
        )
        state = await manager.get_run_state("__test-run-defer")
        assert state["state"] == "DEFERRED"
        assert "deferred_until" in state

    async def test_get_run_state_not_found(self, manager):
        state = await manager.get_run_state("__test-nonexistent-xyz")
        assert state is None


class TestIsTerminalActive:
    def test_is_terminal(self):
        assert RunLifecycleManager.is_terminal(RunState.COMPLETED)
        assert RunLifecycleManager.is_terminal(RunState.FAILED)
        assert not RunLifecycleManager.is_terminal(RunState.QUEUED)

    def test_is_active(self):
        assert RunLifecycleManager.is_active(RunState.QUEUED)
        assert RunLifecycleManager.is_active(RunState.OPTIMIZING)
        assert not RunLifecycleManager.is_active(RunState.COMPLETED)
