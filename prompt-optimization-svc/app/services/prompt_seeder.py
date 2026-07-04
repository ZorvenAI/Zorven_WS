"""Prompt catalog seeder — registers all prompts into MLflow."""

import logging
from dataclasses import dataclass

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
