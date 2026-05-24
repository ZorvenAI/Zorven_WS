"""Optimization run lifecycle state machine (§14.3).

States:
    QUEUED → ACQUIRING_LOCK → LOADING_DATA → OPTIMIZING → VALIDATING
    → CANARY → PROMOTING → COMPLETED

Side states:
    DEFERRED (lock conflict, 1h retry)
    PENDING_APPROVAL (CRITICAL agents)
    REJECTED, ROLLED_BACK, FAILED (terminal)
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

DEFERRED_RETRY_SECONDS = 3600  # 1 hour


class RunState(str, Enum):
    """Optimization run lifecycle states."""

    QUEUED = "QUEUED"
    ACQUIRING_LOCK = "ACQUIRING_LOCK"
    LOADING_DATA = "LOADING_DATA"
    OPTIMIZING = "OPTIMIZING"
    VALIDATING = "VALIDATING"
    CANARY = "CANARY"
    PROMOTING = "PROMOTING"
    COMPLETED = "COMPLETED"
    # Side states
    DEFERRED = "DEFERRED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


# Valid state transitions
VALID_RUN_TRANSITIONS: dict[RunState, set[RunState]] = {
    RunState.QUEUED: {RunState.ACQUIRING_LOCK, RunState.FAILED},
    RunState.ACQUIRING_LOCK: {
        RunState.LOADING_DATA,
        RunState.DEFERRED,
        RunState.FAILED,
    },
    RunState.LOADING_DATA: {RunState.OPTIMIZING, RunState.FAILED},
    RunState.OPTIMIZING: {RunState.VALIDATING, RunState.FAILED},
    RunState.VALIDATING: {
        RunState.CANARY,
        RunState.PENDING_APPROVAL,
        RunState.REJECTED,
        RunState.FAILED,
    },
    RunState.CANARY: {
        RunState.PROMOTING,
        RunState.ROLLED_BACK,
        RunState.FAILED,
    },
    RunState.PROMOTING: {RunState.COMPLETED, RunState.FAILED},
    RunState.COMPLETED: set(),
    RunState.DEFERRED: {RunState.QUEUED, RunState.FAILED},
    RunState.PENDING_APPROVAL: {
        RunState.CANARY,
        RunState.REJECTED,
    },
    RunState.REJECTED: set(),
    RunState.ROLLED_BACK: set(),
    RunState.FAILED: set(),
}

TERMINAL_STATES = {
    RunState.COMPLETED,
    RunState.REJECTED,
    RunState.ROLLED_BACK,
    RunState.FAILED,
}

ACTIVE_STATES = set(RunState) - TERMINAL_STATES

# Kafka event types per state
RUN_EVENT_MAP: dict[RunState, str] = {
    RunState.QUEUED: "optimization.run.queued",
    RunState.ACQUIRING_LOCK: "optimization.run.acquiring_lock",
    RunState.LOADING_DATA: "optimization.run.loading_data",
    RunState.OPTIMIZING: "optimization.run.optimizing",
    RunState.VALIDATING: "optimization.run.validating",
    RunState.CANARY: "optimization.run.canary",
    RunState.PROMOTING: "optimization.run.promoting",
    RunState.COMPLETED: "optimization.run.completed",
    RunState.DEFERRED: "optimization.run.deferred",
    RunState.PENDING_APPROVAL: "optimization.run.pending_approval",
    RunState.REJECTED: "optimization.run.rejected",
    RunState.ROLLED_BACK: "optimization.run.rolled_back",
    RunState.FAILED: "optimization.run.failed",
}


class InvalidRunTransitionError(Exception):
    """Raised when a run state transition is not allowed."""

    def __init__(self, from_state: RunState, to_state: RunState):
        self.from_state = from_state
        self.to_state = to_state
        allowed = VALID_RUN_TRANSITIONS.get(from_state, set())
        super().__init__(
            f"Invalid run transition: {from_state.value} → {to_state.value}. "
            f"Allowed: {', '.join(s.value for s in allowed) or 'none'}"
        )


class RunLifecycleManager:
    """Manages optimization run lifecycle transitions.

    Persists state to Redis progress hash and emits Kafka events.
    """

    def __init__(
        self,
        prompt_cache=None,
        lifecycle_producer=None,
    ) -> None:
        self.prompt_cache = prompt_cache
        self.producer = lifecycle_producer

    def validate_transition(
        self, from_state: RunState, to_state: RunState
    ) -> bool:
        """Check if a run state transition is valid."""
        allowed = VALID_RUN_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise InvalidRunTransitionError(from_state, to_state)
        return True

    async def transition(
        self,
        run_id: str,
        from_state: RunState,
        to_state: RunState,
        prompt_name: str = "",
        agent_code: str = "",
        error_message: str = "",
    ) -> bool:
        """Execute a run state transition with persistence and events."""
        self.validate_transition(from_state, to_state)

        # AC-1: Persist to Redis progress hash
        if self.prompt_cache is not None:
            progress = {
                "state": to_state.value,
                "prompt_name": prompt_name,
                "agent_code": agent_code,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if error_message:
                progress["error_message"] = error_message
            await self.prompt_cache.set_optimization_progress(
                run_id, progress
            )

        # AC-3: Emit Kafka event
        event_type = RUN_EVENT_MAP.get(
            to_state, "optimization.run.state_changed"
        )
        if self.producer is not None:
            self.producer.send_lifecycle_event_sync(
                event_type=event_type,
                prompt_name=prompt_name,
                version=0,
                from_state=from_state.value,
                to_state=to_state.value,
            )

        logger.info(
            "Run %s: %s → %s (prompt=%s, agent=%s)",
            run_id,
            from_state.value,
            to_state.value,
            prompt_name,
            agent_code,
        )
        return True

    async def defer_on_lock_conflict(
        self, run_id: str, prompt_name: str = "", agent_code: str = ""
    ) -> datetime:
        """AC-2: Transition to DEFERRED with 1h retry time."""
        await self.transition(
            run_id,
            RunState.ACQUIRING_LOCK,
            RunState.DEFERRED,
            prompt_name=prompt_name,
            agent_code=agent_code,
        )
        retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=DEFERRED_RETRY_SECONDS
        )

        # Update progress with retry time
        if self.prompt_cache is not None:
            await self.prompt_cache.set_optimization_progress(
                run_id,
                {
                    "state": RunState.DEFERRED.value,
                    "deferred_until": retry_at.isoformat(),
                    "prompt_name": prompt_name,
                },
            )

        logger.info(
            "Run %s deferred — retry at %s",
            run_id,
            retry_at.isoformat(),
        )
        return retry_at

    async def get_run_state(self, run_id: str) -> Optional[dict]:
        """Get current run state from Redis progress hash."""
        if self.prompt_cache is None:
            return None
        return await self.prompt_cache.get_optimization_progress(run_id)

    @staticmethod
    def is_terminal(state: RunState) -> bool:
        """Check if a state is terminal (no outgoing transitions)."""
        return state in TERMINAL_STATES

    @staticmethod
    def is_active(state: RunState) -> bool:
        """Check if a state is active (has outgoing transitions)."""
        return state in ACTIVE_STATES
