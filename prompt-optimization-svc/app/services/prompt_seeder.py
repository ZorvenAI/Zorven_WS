"""Prompt catalog seeder — registers all prompts into MLflow."""

import logging
from dataclasses import dataclass

from app.logic.lifecycle import PromptLifecycleManager, PromptState
from app.registries.prompt_catalog import PROMPT_CATALOG
from app.services.mlflow_registry import MLflowPromptRegistry

logger = logging.getLogger(__name__)


@dataclass
class SeedResult:
    """Summary of a seeding operation."""

    created: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.details is None:
            self.details = []


def seed_prompt_catalog(registry: MLflowPromptRegistry) -> SeedResult:
    """Register all prompts from the catalog into MLflow.

    Skips prompts that already exist. Each prompt is tagged with
    state=DRAFT at version 1.
    """
    result = SeedResult()

    for entry in PROMPT_CATALOG:
        try:
            if registry.prompt_exists(entry.name):
                result.skipped += 1
                result.details.append(f"SKIP: {entry.name} (already exists)")
                continue

            registry.register_prompt(
                name=entry.name,
                template=entry.template,
                tags=entry.tags,
            )
            result.created += 1
            result.details.append(f"CREATED: {entry.name}")
        except Exception as exc:
            result.errors += 1
            result.details.append(f"ERROR: {entry.name} — {exc}")
            logger.error("Failed to seed prompt %s: %s", entry.name, exc)

    logger.info(
        "Prompt seeding complete: %d created, %d skipped, %d errors",
        result.created,
        result.skipped,
        result.errors,
    )
    return result


# Transition path from each state to reach PRODUCTION
_REMAINING_TRANSITIONS: dict[PromptState, list[PromptState]] = {
    PromptState.DRAFT: [
        PromptState.STAGING,
        PromptState.CANARY,
        PromptState.PRODUCTION,
    ],
    PromptState.STAGING: [PromptState.CANARY, PromptState.PRODUCTION],
    PromptState.CANARY: [PromptState.PRODUCTION],
}


def seed_to_production(
    registry: MLflowPromptRegistry,
    lifecycle_manager: PromptLifecycleManager,
) -> SeedResult:
    """Register all catalog prompts and promote them to PRODUCTION.

    Walks each prompt through the full lifecycle (DRAFT→STAGING→CANARY→PRODUCTION).
    Handles crash recovery — if a prompt is stuck at an intermediate state from
    a prior partial run, it resumes from that state.

    Args:
        registry: MLflow registry for prompt CRUD.
        lifecycle_manager: Lifecycle manager for state transitions.

    Returns:
        SeedResult with promoted count in ``created``, already-PRODUCTION in
        ``skipped``, and failures in ``errors``.
    """
    result = SeedResult()

    for entry in PROMPT_CATALOG:
        try:
            # Check if already at PRODUCTION
            prod = registry.get_prompt_by_state(
                entry.name, PromptState.PRODUCTION.value
            )
            if prod is not None:
                result.skipped += 1
                result.details.append(f"SKIP: {entry.name} (already PRODUCTION)")
                continue

            # Determine current state
            prompt_info = registry.get_prompt(entry.name)
            if prompt_info is None:
                # Not registered yet — register as DRAFT
                prompt_info = registry.register_prompt(
                    name=entry.name,
                    template=entry.template,
                    tags=entry.tags,
                )
                current_state = PromptState.DRAFT
            else:
                state_tag = prompt_info.tags.get("state", "DRAFT")
                try:
                    current_state = PromptState(state_tag)
                except ValueError:
                    result.errors += 1
                    result.details.append(
                        f"ERROR: {entry.name} — unknown state '{state_tag}'"
                    )
                    logger.warning(
                        "Skipping %s: unknown state '%s'", entry.name, state_tag
                    )
                    continue

            # Get remaining transitions
            transitions = _REMAINING_TRANSITIONS.get(current_state)
            if transitions is None:
                # State not in the happy path (REJECTED, ROLLED_BACK, etc.)
                result.errors += 1
                result.details.append(
                    f"ERROR: {entry.name} — cannot promote from {current_state.value}"
                )
                logger.warning(
                    "Cannot promote %s from state %s",
                    entry.name,
                    current_state.value,
                )
                continue

            # Walk through remaining transitions
            prev_state = current_state
            for target_state in transitions:
                if target_state == PromptState.PRODUCTION:
                    lifecycle_manager.promote_to_production(
                        entry.name, prompt_info.version
                    )
                else:
                    lifecycle_manager.transition(
                        entry.name,
                        prompt_info.version,
                        prev_state,
                        target_state,
                    )
                prev_state = target_state

            result.created += 1
            result.details.append(f"PROMOTED: {entry.name} v{prompt_info.version}")

        except Exception as exc:
            result.errors += 1
            result.details.append(f"ERROR: {entry.name} — {exc}")
            logger.error(
                "Failed to seed-to-production %s: %s", entry.name, exc, exc_info=True
            )

    logger.info(
        "Seed-to-production complete: %d promoted, %d skipped, %d errors",
        result.created,
        result.skipped,
        result.errors,
    )
    return result
