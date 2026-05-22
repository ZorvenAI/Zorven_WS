"""Prompt version lifecycle state machine (§3.3).

States:
    DRAFT → STAGING → CANARY → PRODUCTION → ARCHIVED
    STAGING → REJECTED (optimization didn't improve)
    CANARY → ROLLED_BACK (regression detected)
    PRODUCTION → ROLLED_BACK (manual rollback)
    DRAFT → TENANT_OVERRIDE → ARCHIVED (tenant-specific path)
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class PromptState(str, Enum):
    """Prompt version lifecycle states."""

    DRAFT = "DRAFT"
    STAGING = "STAGING"
    CANARY = "CANARY"
    PRODUCTION = "PRODUCTION"
    ARCHIVED = "ARCHIVED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"
    TENANT_OVERRIDE = "TENANT_OVERRIDE"


# Valid state transitions: from_state -> set of allowed to_states
VALID_TRANSITIONS: dict[PromptState, set[PromptState]] = {
    PromptState.DRAFT: {PromptState.STAGING, PromptState.TENANT_OVERRIDE},
    PromptState.STAGING: {PromptState.CANARY, PromptState.REJECTED},
    PromptState.CANARY: {PromptState.PRODUCTION, PromptState.ROLLED_BACK},
    PromptState.PRODUCTION: {PromptState.ARCHIVED, PromptState.ROLLED_BACK},
    PromptState.ARCHIVED: set(),
    PromptState.REJECTED: set(),
    PromptState.ROLLED_BACK: set(),
    PromptState.TENANT_OVERRIDE: {PromptState.ARCHIVED},
}

# States that are served to production agents
SERVABLE_STATES = {
    PromptState.PRODUCTION,
    PromptState.TENANT_OVERRIDE,
    PromptState.CANARY,
}

# Event type names for Kafka
STATE_EVENT_MAP: dict[PromptState, str] = {
    PromptState.STAGING: "prompt.staged",
    PromptState.CANARY: "prompt.canary_started",
    PromptState.PRODUCTION: "prompt.promoted",
    PromptState.ARCHIVED: "prompt.archived",
    PromptState.REJECTED: "prompt.rejected",
    PromptState.ROLLED_BACK: "prompt.rolled_back",
    PromptState.TENANT_OVERRIDE: "prompt.tenant_override",
}


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, from_state: PromptState, to_state: PromptState):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid transition: {from_state.value} → {to_state.value}. "
            f"Allowed from {from_state.value}: "
            f"{', '.join(s.value for s in VALID_TRANSITIONS.get(from_state, set())) or 'none'}"
        )


class PromptLifecycleManager:
    """Manages prompt version lifecycle transitions.

    Delegates state persistence to MLflowPromptRegistry and emits
    Kafka events via LifecycleProducer.
    """

    def __init__(self, registry, lifecycle_producer=None):
        """
        Args:
            registry: MLflowPromptRegistry instance for state persistence.
            lifecycle_producer: Optional LifecycleProducer for Kafka events.
        """
        self.registry = registry
        self.producer = lifecycle_producer

    def validate_transition(
        self, from_state: PromptState, to_state: PromptState
    ) -> bool:
        """Check if a state transition is valid.

        Returns True if valid, raises InvalidTransitionError otherwise.
        """
        allowed = VALID_TRANSITIONS.get(from_state, set())
        if to_state not in allowed:
            raise InvalidTransitionError(from_state, to_state)
        return True

    def transition(
        self,
        name: str,
        version: int,
        from_state: PromptState,
        to_state: PromptState,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Execute a state transition with validation and event emission.

        Args:
            name: Prompt name.
            version: Prompt version number.
            from_state: Current state.
            to_state: Target state.
            tenant_id: Optional tenant for scoping.

        Returns:
            True on success.

        Raises:
            InvalidTransitionError: If the transition is not allowed.
        """
        self.validate_transition(from_state, to_state)

        # Persist state change
        self.registry.set_prompt_state(name, version, to_state.value)

        # Emit Kafka event (AC-6)
        event_type = STATE_EVENT_MAP.get(to_state, f"prompt.state_changed")
        if self.producer:
            self.producer.send_lifecycle_event_sync(
                event_type=event_type,
                prompt_name=name,
                version=version,
                from_state=from_state.value,
                to_state=to_state.value,
                tenant_id=tenant_id,
            )

        logger.info(
            "Lifecycle transition: %s v%d %s → %s (tenant=%s)",
            name,
            version,
            from_state.value,
            to_state.value,
            tenant_id,
        )
        return True

    def promote_to_production(
        self,
        name: str,
        version: int,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Promote a CANARY version to PRODUCTION.

        AC-1: Only one PRODUCTION per prompt per tenant.
        AC-2: Auto-archives the previous PRODUCTION version.
        """
        # Find and archive current PRODUCTION (AC-2)
        current_prod = self.registry.get_prompt_by_state(
            name, PromptState.PRODUCTION.value, tenant_id=tenant_id
        )
        if current_prod is not None:
            self.transition(
                name,
                current_prod.version,
                PromptState.PRODUCTION,
                PromptState.ARCHIVED,
                tenant_id=tenant_id,
            )

        # Promote new version
        return self.transition(
            name,
            version,
            PromptState.CANARY,
            PromptState.PRODUCTION,
            tenant_id=tenant_id,
        )

    def reject(self, name: str, version: int) -> bool:
        """Reject a STAGING version. AC-3: Never hard-deleted."""
        return self.transition(name, version, PromptState.STAGING, PromptState.REJECTED)

    def rollback(
        self,
        name: str,
        version: int,
        current_state: PromptState,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Roll back a CANARY or PRODUCTION version."""
        return self.transition(
            name,
            version,
            current_state,
            PromptState.ROLLED_BACK,
            tenant_id=tenant_id,
        )

    def get_production_version(
        self,
        name: str,
        tenant_id: Optional[str] = None,
    ):
        """Get the current production version.

        AC-5: TENANT_OVERRIDE takes precedence over global PRODUCTION.
        AC-4: STAGING versions are never returned.
        """
        if tenant_id:
            # Check tenant override first
            override = self.registry.get_prompt_by_state(
                name, PromptState.TENANT_OVERRIDE.value, tenant_id=tenant_id
            )
            if override is not None:
                return override

        # Fall back to global PRODUCTION
        return self.registry.get_prompt_by_state(
            name, PromptState.PRODUCTION.value, tenant_id=None
        )

    @staticmethod
    def is_servable(state: PromptState) -> bool:
        """Check if a state is served to production agents.

        AC-4: STAGING is NOT servable.
        """
        return state in SERVABLE_STATES
