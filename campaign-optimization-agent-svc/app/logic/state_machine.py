"""Per-campaign tick state machine for Campaign Optimization Agent.

States from design doc section 7.2 covering the full optimization lifecycle.
Each campaign in a tick transitions through these states sequentially,
with error states branching to ROLLBACK, ESCALATED, or SKIPPED.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TickState(str, Enum):
    """Per-campaign tick states."""

    DISCOVERING = "discovering"
    FETCHING_INSIGHTS = "fetching_insights"
    SKIPPED = "skipped"
    ANALYZING = "analyzing"
    NO_ACTION = "no_action"
    RECOMMENDING = "recommending"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    PERSISTING = "persisting"
    COMPLETED = "completed"
    ROLLBACK = "rollback"
    ESCALATED = "escalated"
    REJECTED = "rejected"
    EXPIRED = "expired"
    IDLE = "idle"


# Valid state transitions
TRANSITIONS: dict[TickState, list[TickState]] = {
    TickState.IDLE: [TickState.DISCOVERING],
    TickState.DISCOVERING: [
        TickState.FETCHING_INSIGHTS,
        TickState.SKIPPED,
    ],
    TickState.FETCHING_INSIGHTS: [
        TickState.ANALYZING,
        TickState.SKIPPED,
        TickState.ESCALATED,
    ],
    TickState.ANALYZING: [
        TickState.RECOMMENDING,
        TickState.NO_ACTION,
        TickState.SKIPPED,
    ],
    TickState.NO_ACTION: [TickState.PERSISTING, TickState.COMPLETED],
    TickState.RECOMMENDING: [
        TickState.AWAITING_APPROVAL,
        TickState.EXECUTING,
        TickState.SKIPPED,
    ],
    TickState.AWAITING_APPROVAL: [
        TickState.EXECUTING,
        TickState.REJECTED,
        TickState.EXPIRED,
    ],
    TickState.EXECUTING: [
        TickState.VERIFYING,
        TickState.ROLLBACK,
        TickState.ESCALATED,
    ],
    TickState.VERIFYING: [
        TickState.PERSISTING,
        TickState.ROLLBACK,
        TickState.ESCALATED,
    ],
    TickState.PERSISTING: [TickState.COMPLETED, TickState.ESCALATED],
    TickState.ROLLBACK: [TickState.ESCALATED, TickState.COMPLETED],
    TickState.COMPLETED: [TickState.IDLE],
    TickState.SKIPPED: [TickState.IDLE],
    TickState.ESCALATED: [TickState.IDLE],
    TickState.REJECTED: [TickState.IDLE],
    TickState.EXPIRED: [TickState.IDLE],
}


class CampaignTickStateMachine:
    """Manages state transitions for a single campaign during a tick."""

    def __init__(self, campaign_id: str):
        self.campaign_id = campaign_id
        self.state = TickState.IDLE
        self._history: list[dict[str, Any]] = []

    def transition(self, new_state: TickState, reason: str = "") -> bool:
        """Attempt to transition to a new state.

        Returns True if the transition was valid, False otherwise.
        """
        valid_targets = TRANSITIONS.get(self.state, [])
        if new_state not in valid_targets:
            logger.warning(
                "Invalid state transition for campaign %s: %s -> %s "
                "(valid: %s)",
                self.campaign_id,
                self.state.value,
                new_state.value,
                [s.value for s in valid_targets],
            )
            return False

        old_state = self.state
        self.state = new_state
        self._history.append(
            {
                "from": old_state.value,
                "to": new_state.value,
                "reason": reason,
            }
        )
        logger.debug(
            "Campaign %s: %s -> %s (%s)",
            self.campaign_id,
            old_state.value,
            new_state.value,
            reason,
        )
        return True

    @property
    def is_terminal(self) -> bool:
        """True if the current state is a terminal state."""
        return self.state in (
            TickState.COMPLETED,
            TickState.SKIPPED,
            TickState.ESCALATED,
            TickState.REJECTED,
            TickState.EXPIRED,
            TickState.NO_ACTION,
        )

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return the state transition history."""
        return list(self._history)
