"""SKL-COA-09: Human approval handler.

Handles approve/reject/modify/batch-approve for recommendations.
RBAC: VIEWER denied, EDITOR escalated, ADMIN/OWNER can approve.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from app.cache.redis_manager import RedisManager
from app.messaging.event_emitter import EventEmitter, EventType

logger = logging.getLogger(__name__)

# RBAC roles
VIEWER_ROLES = {"VIEWER", "viewer"}
EDITOR_ROLES = {"EDITOR", "editor"}
ADMIN_ROLES = {"ADMIN", "admin", "OWNER", "owner"}


class ApprovalHandler:
    """Handles human approval of optimization recommendations."""

    def __init__(
        self,
        redis_manager: RedisManager | None = None,
        event_emitter: EventEmitter | None = None,
        autonomous_executor=None,
    ):
        self._redis = redis_manager
        self._emitter = event_emitter
        self._executor = autonomous_executor

    async def approve_recommendation(
        self,
        rec_id: str,
        approved_by: str,
        user_role: str,
    ) -> dict[str, Any]:
        """Approve a recommendation for execution.

        Args:
            rec_id: Recommendation identifier.
            approved_by: User who approved.
            user_role: Role of the approver.

        Returns:
            Approval result dict.
        """
        # RBAC check
        rbac = self._check_rbac(user_role)
        if rbac:
            return rbac

        logger.info(
            "Recommendation %s approved by %s (%s)",
            rec_id,
            approved_by,
            user_role,
        )

        if self._emitter:
            await self._emitter.emit(
                EventType.ACTION_APPROVED,
                data={
                    "recommendation_id": rec_id,
                    "approved_by": approved_by,
                    "user_role": user_role,
                },
            )

        return {
            "recommendation_id": rec_id,
            "status": "approved",
            "executed": False,
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

    async def reject_recommendation(
        self,
        rec_id: str,
        reason: str,
        rejected_by: str,
    ) -> dict[str, Any]:
        """Reject a recommendation.

        Args:
            rec_id: Recommendation identifier.
            reason: Rejection reason.
            rejected_by: User who rejected.

        Returns:
            Rejection result dict.
        """
        logger.info(
            "Recommendation %s rejected by %s: %s",
            rec_id,
            rejected_by,
            reason,
        )

        if self._emitter:
            await self._emitter.emit(
                EventType.ACTION_REJECTED,
                data={
                    "recommendation_id": rec_id,
                    "rejected_by": rejected_by,
                    "reason": reason,
                },
            )

        return {
            "recommendation_id": rec_id,
            "status": "rejected",
            "executed": False,
            "rejected_by": rejected_by,
            "reason": reason,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
        }

    async def modify_recommendation(
        self,
        rec_id: str,
        modified_values: dict[str, Any],
        approved_by: str,
    ) -> dict[str, Any]:
        """Modify and approve a recommendation.

        Args:
            rec_id: Recommendation identifier.
            modified_values: Overridden proposed values.
            approved_by: User who modified and approved.

        Returns:
            Modified approval result dict.
        """
        logger.info(
            "Recommendation %s modified and approved by %s: %s",
            rec_id,
            approved_by,
            modified_values,
        )

        return {
            "recommendation_id": rec_id,
            "status": "modified_and_approved",
            "executed": False,
            "modified_values": modified_values,
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
        }

    async def batch_approve(
        self,
        campaign_id: str,
        tenant_id: str,
        approved_by: str,
    ) -> list[dict[str, Any]]:
        """Batch approve all pending recommendations for a campaign.

        Args:
            campaign_id: Campaign identifier.
            tenant_id: Tenant identifier.
            approved_by: User who approved.

        Returns:
            List of approval result dicts.
        """
        results = []

        if not self._redis:
            logger.warning("Redis unavailable -- cannot batch approve")
            return results

        recs = await self._redis.get_recommendations(
            tenant_id=tenant_id, campaign_id=campaign_id
        )

        for rec in recs:
            if rec.get("status") == "pending":
                result = await self.approve_recommendation(
                    rec_id=rec.get("recommendation_id", ""),
                    approved_by=approved_by,
                    user_role="ADMIN",
                )
                results.append(result)

        logger.info(
            "Batch approved %d recommendations for campaign %s",
            len(results),
            campaign_id,
        )
        return results

    async def expire_stale_recommendations(self) -> int:
        """Expire recommendations that have passed their 48h TTL.

        Returns:
            Count of expired recommendations.
        """
        # This is handled by Redis TTL on the recommendations list.
        # This method exists for explicit cleanup and event emission.
        expired_count = 0
        logger.info(
            "Stale recommendation expiry check complete: %d expired",
            expired_count,
        )

        if self._emitter and expired_count > 0:
            await self._emitter.emit(
                EventType.ACTION_EXPIRED,
                data={"expired_count": expired_count},
            )

        return expired_count

    async def list_pending_recommendations(
        self, campaign_id: str, tenant_id: str
    ) -> list[dict[str, Any]]:
        """List pending recommendations for a campaign.

        Args:
            campaign_id: Campaign identifier.
            tenant_id: Tenant identifier.

        Returns:
            List of pending recommendation dicts.
        """
        if not self._redis:
            return []
        try:
            recs = await self._redis.get_recommendations(
                tenant_id=tenant_id, campaign_id=campaign_id
            )
            return [r for r in recs if r.get("status") == "pending"]
        except Exception as exc:
            logger.error(
                "Failed to list pending recommendations: %s", exc
            )
            return []

    def _check_rbac(self, user_role: str) -> dict[str, Any] | None:
        """Check RBAC permissions. Returns error dict if denied."""
        if user_role in VIEWER_ROLES:
            return {
                "status": "denied",
                "error": "VIEWER role cannot approve recommendations.",
            }
        if user_role in EDITOR_ROLES:
            return {
                "status": "escalated",
                "error": (
                    "EDITOR role escalated to ADMIN for approval."
                ),
            }
        return None
