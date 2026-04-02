"""Rollback manager for Meta Ads entities.

Tracks all created entity IDs during a publishing session and
rolls back (pauses) them in reverse creation order on failure.
Entities are PAUSED, never deleted.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RollbackManager:
    """Tracks and rolls back Meta Ads entities on failure."""

    def __init__(self):
        self._entities: list[dict[str, str]] = []

    @property
    def entities(self) -> list[dict[str, str]]:
        """All tracked entities."""
        return list(self._entities)

    def track(self, entity_type: str, entity_id: str):
        """Register a created entity for potential rollback.

        Parameters
        ----------
        entity_type : str
            One of "campaign", "ad_set", "ad", "creative".
        entity_id : str
            The Meta entity ID.
        """
        self._entities.append({"type": entity_type, "id": entity_id})
        logger.debug("Tracked %s %s for rollback", entity_type, entity_id)

    async def rollback_all(
        self,
        meta_client,
        reason: str,
    ) -> dict[str, Any]:
        """Pause all tracked entities in reverse creation order.

        Returns a summary dict with results per entity.
        """
        if not self._entities:
            return {"rolled_back": 0, "results": [], "reason": reason}

        # Only pause campaigns and ad sets (ads don't need separate pause)
        pausable = [
            e
            for e in self._entities
            if e["type"] in ("campaign", "ad_set")
        ]

        logger.warning(
            "ROLLBACK: Pausing %d entities (reason: %s)", len(pausable), reason
        )

        results = await meta_client.pause_entities(pausable)

        return {
            "rolled_back": len(results),
            "results": results,
            "reason": reason,
            "total_tracked": len(self._entities),
        }

    def clear(self):
        """Clear tracked entities (after successful publish)."""
        self._entities.clear()
