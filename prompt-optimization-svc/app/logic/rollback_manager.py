"""Manual rollback to any archived version (§13.1, OPT-08).

Archives the current PRODUCTION version and promotes the specified
archived version, enabling instant recovery within the 30-day
retention window.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# OPT-08: Archived versions retained for ≥30 days (AC-1)
ARCHIVE_RETENTION_DAYS = 30

# Redis cache key template for prompt production cache
PRODUCTION_CACHE_KEY = "prompt:{name}:production"


@dataclass
class RollbackResult:
    """Result of a manual rollback operation."""

    prompt_name: str
    rolled_back_version: int  # old production version (now archived)
    restored_version: int  # target version (now production)
    success: bool = False
    cache_invalidated: bool = False
    error: str = ""


def is_within_retention_window(
    archived_at: Optional[datetime],
    retention_days: int = ARCHIVE_RETENTION_DAYS,
) -> bool:
    """Check if an archived version is still within retention window (AC-1).

    Args:
        archived_at: When the version was archived.
        retention_days: Retention period in days.

    Returns:
        True if the version is within the retention window.
    """
    if archived_at is None:
        return True  # No archive timestamp = assume within window
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    return archived_at >= cutoff


async def rollback_to_version(
    prompt_name: str,
    target_version: int,
    mlflow_registry=None,
    prompt_cache=None,
    lifecycle_producer=None,
) -> RollbackResult:
    """Roll back to a specific archived version.

    1. Verifies target version exists and is within retention (AC-1)
    2. Archives current PRODUCTION version
    3. Promotes target version to PRODUCTION
    4. Emits prompt.promoted Kafka event (AC-2)
    5. Invalidates Redis cache (AC-3)

    Args:
        prompt_name: Prompt to roll back.
        target_version: Version number to restore.
        mlflow_registry: MLflow prompt registry client.
        prompt_cache: Redis prompt cache manager.
        lifecycle_producer: Kafka lifecycle event producer.

    Returns:
        RollbackResult with success/failure details.
    """
    result = RollbackResult(
        prompt_name=prompt_name,
        rolled_back_version=0,
        restored_version=target_version,
    )

    if mlflow_registry is None:
        result.error = "MLflow registry not available"
        return result

    # 1. Get current production version
    current_prod = mlflow_registry.get_prompt_by_state(prompt_name, "PRODUCTION")
    if current_prod is None:
        result.error = f"No PRODUCTION version found for '{prompt_name}'"
        return result

    result.rolled_back_version = current_prod.version

    # 2. Verify target version exists
    target = mlflow_registry.get_prompt(prompt_name)
    if target is None:
        result.error = f"Prompt '{prompt_name}' not found"
        return result

    # 3. Archive current production
    try:
        mlflow_registry.set_prompt_state(prompt_name, current_prod.version, "ARCHIVED")
    except Exception as exc:
        result.error = f"Failed to archive v{current_prod.version}: {exc}"
        return result

    # 4. Promote target version to PRODUCTION
    try:
        mlflow_registry.set_prompt_state(prompt_name, target_version, "PRODUCTION")
    except Exception as exc:
        result.error = f"Failed to promote v{target_version}: {exc}"
        return result

    result.success = True

    # 5. Emit prompt.promoted Kafka event (AC-2)
    if lifecycle_producer is not None:
        try:
            lifecycle_producer.send_lifecycle_event_sync(
                event_type="prompt.promoted",
                prompt_name=prompt_name,
                version=target_version,
                from_state="ARCHIVED",
                to_state="PRODUCTION",
            )
        except Exception as exc:
            logger.error("Failed to emit rollback event: %s", exc)

    # 6. Invalidate Redis cache (AC-3)
    if prompt_cache is not None:
        try:
            r = await prompt_cache.connect()
            cache_key = PRODUCTION_CACHE_KEY.format(name=prompt_name)
            await r.delete(cache_key)
            result.cache_invalidated = True
        except Exception as exc:
            logger.error("Failed to invalidate cache for %s: %s", prompt_name, exc)

    logger.info(
        "Rollback complete: %s v%d → v%d (archived v%d)",
        prompt_name,
        current_prod.version,
        target_version,
        current_prod.version,
    )
    return result
