"""SKL-COA-10: Optimization verification.

Verifies Meta API writes by reading back entities and comparing
to expected state. Single retry on mismatch, then ESCALATE.
Tracks cumulative spend impact (>30% -> PAUSE remaining).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OptimizationVerifier:
    """Verifies Meta API writes after execution."""

    def __init__(self):
        self._cumulative_spend_impact_pct: float = 0.0

    async def verify_action(
        self,
        entity_type: str,
        entity_id: str,
        expected_state: dict[str, Any],
        meta_client: Any,
        access_token: str = "",
    ) -> dict[str, Any]:
        """Verify a Meta API write by reading back the entity.

        Args:
            entity_type: One of 'campaign', 'ad_set', 'ad'.
            entity_id: Meta entity ID.
            expected_state: Expected state after the write.
            meta_client: MetaManagementClient instance.
            access_token: Meta access token.

        Returns:
            VerificationResult dict with verified status.
        """
        try:
            actual = await meta_client.read_back_entity(
                entity_type=entity_type,
                entity_id=entity_id,
                access_token=access_token,
            )

            if not actual:
                logger.warning(
                    "Read-back returned empty for %s %s",
                    entity_type,
                    entity_id,
                )
                return {
                    "verified": False,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "reason": "read_back_empty",
                    "retry": True,
                }

            # Compare expected vs actual
            mismatches = self._compare_states(expected_state, actual)

            if not mismatches:
                return {
                    "verified": True,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "actual_state": actual,
                }

            # Single retry on mismatch
            logger.warning(
                "Verification mismatch for %s %s: %s. Retrying...",
                entity_type,
                entity_id,
                mismatches,
            )
            actual_retry = await meta_client.read_back_entity(
                entity_type=entity_type,
                entity_id=entity_id,
                access_token=access_token,
            )
            mismatches_retry = self._compare_states(
                expected_state, actual_retry
            )

            if not mismatches_retry:
                return {
                    "verified": True,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "actual_state": actual_retry,
                    "note": "verified_on_retry",
                }

            # Retry failed -> ESCALATE
            logger.error(
                "Verification FAILED after retry for %s %s: %s",
                entity_type,
                entity_id,
                mismatches_retry,
            )
            return {
                "verified": False,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "mismatches": mismatches_retry,
                "escalate": True,
                "reason": "mismatch_after_retry",
            }

        except Exception as exc:
            logger.error(
                "Verification error for %s %s: %s",
                entity_type,
                entity_id,
                exc,
            )
            return {
                "verified": False,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "error": str(exc),
                "escalate": True,
            }

    def track_spend_impact(self, impact_pct: float) -> bool:
        """Track cumulative spend impact.

        Args:
            impact_pct: Spend impact percentage of this action.

        Returns:
            True if cumulative impact exceeds 30% (should pause).
        """
        self._cumulative_spend_impact_pct += impact_pct
        if self._cumulative_spend_impact_pct > 30:
            logger.warning(
                "Cumulative spend impact %.1f%% exceeds 30%% -- "
                "PAUSE remaining actions",
                self._cumulative_spend_impact_pct,
            )
            return True
        return False

    @property
    def cumulative_spend_impact(self) -> float:
        """Current cumulative spend impact percentage."""
        return self._cumulative_spend_impact_pct

    def reset_spend_tracking(self):
        """Reset cumulative spend tracking for a new tick."""
        self._cumulative_spend_impact_pct = 0.0

    def _compare_states(
        self,
        expected: dict[str, Any],
        actual: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Compare expected vs actual state. Returns list of mismatches."""
        mismatches = []
        for key, expected_val in expected.items():
            actual_val = actual.get(key)
            if actual_val is not None and str(actual_val) != str(
                expected_val
            ):
                mismatches.append(
                    {
                        "field": key,
                        "expected": expected_val,
                        "actual": actual_val,
                    }
                )
        return mismatches
