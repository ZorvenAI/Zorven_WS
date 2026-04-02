"""Mandatory human approval gate for ad publishing.

HARDCODED: Every ad creation request MUST be approved by a human.
This is NOT a configurable guardrail — it is core business logic.

Flow:
1. Store approval request in Redis with 24h TTL
2. Return approval_request_id to caller
3. Wait for /v1/approve call with user decision
4. On approve: continue to publish phase
5. On reject: mark as rejected, emit audit event
6. On expiry (24h): auto-rejected

Supports:
- Approve All: approve entire campaign
- Approve Selected: approve specific ad sets (partial)
- Reject: reject with optional feedback
- Production mode: additional confirmation step
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ApprovalManager:
    """Manages the mandatory human approval lifecycle."""

    def __init__(self, redis_manager=None, expiry_seconds: int = 86400):
        self._redis = redis_manager
        self._expiry = expiry_seconds
        # In-memory fallback for testing without Redis
        self._memory_store: dict[str, dict[str, Any]] = {}

    async def create_approval_request(
        self,
        job_id: str,
        tenant_id: str,
        preview_data: dict[str, Any],
        is_production: bool,
        callback_url: str = "",
    ) -> dict[str, Any]:
        """Create a new approval request and store it.

        Returns the full approval request dict including request_id.
        """
        request_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        request = {
            "request_id": request_id,
            "job_id": job_id,
            "tenant_id": tenant_id,
            "status": "pending",
            "preview_data": preview_data,
            "is_production": is_production,
            "callback_url": callback_url,
            "created_at": now.isoformat(),
            "expires_at": datetime.fromtimestamp(
                now.timestamp() + self._expiry, tz=timezone.utc
            ).isoformat(),
            "decision": None,
            "approved_ad_sets": None,
            "feedback": None,
            "approved_by": None,
            "approved_at": None,
            "production_confirmed": False,
        }

        if self._redis:
            await self._redis.store_approval_request(
                tenant_id, request_id, request
            )
        else:
            self._memory_store[request_id] = request

        logger.info(
            "Approval request created: id=%s, job=%s, tenant=%s, "
            "production=%s",
            request_id,
            job_id,
            tenant_id,
            is_production,
        )

        return request

    async def process_approval(
        self,
        request_id: str,
        tenant_id: str,
        decision: str,
        approved_ad_sets: list[str] | None = None,
        feedback: str = "",
        approved_by: str = "",
        user_role: str = "VIEWER",
        production_confirmed: bool = False,
    ) -> dict[str, Any]:
        """Process a human approval decision.

        Parameters
        ----------
        decision : str
            One of "approve_all", "approve_selected", "reject".
        approved_ad_sets : list
            For partial approval — which ad set names/IDs to publish.
        feedback : str
            Rejection feedback text.
        approved_by : str
            User ID of the approver.
        user_role : str
            RBAC role (OWNER, ADMIN, EDITOR, VIEWER).
        production_confirmed : bool
            Required True for production mode.

        Returns
        -------
        dict with updated approval state.
        """
        # RBAC: VIEWER cannot approve
        if user_role == "VIEWER":
            return {
                "error": "VIEWER role cannot approve ad publishing",
                "status": "denied",
            }

        # Fetch existing request
        request = await self.get_approval_request(request_id, tenant_id)
        if not request:
            return {"error": "Approval request not found", "status": "error"}

        if request["status"] != "pending":
            return {
                "error": f"Request already {request['status']}",
                "status": request["status"],
            }

        # Check expiry
        expires_at = datetime.fromisoformat(request["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            request["status"] = "expired"
            await self._save(request_id, tenant_id, request)
            return {"status": "expired", "error": "Approval request expired"}

        now = datetime.now(timezone.utc).isoformat()

        if decision == "reject":
            request["status"] = "rejected"
            request["feedback"] = feedback
            request["approved_by"] = approved_by
            request["approved_at"] = now
        elif decision == "approve_all":
            # EDITOR triggers ESCALATION for actual publishing
            if user_role == "EDITOR":
                request["status"] = "escalated"
                request["approved_by"] = approved_by
                request["approved_at"] = now
                request["feedback"] = (
                    "EDITOR approval — requires ADMIN/OWNER to publish"
                )
            else:
                # Production double-confirm
                if request["is_production"] and not production_confirmed:
                    return {
                        "status": "requires_production_confirm",
                        "message": (
                            "LIVE ADS — REAL MONEY. "
                            "Set production_confirmed=true to confirm."
                        ),
                    }
                request["status"] = "approved"
                request["approved_by"] = approved_by
                request["approved_at"] = now
                request["production_confirmed"] = production_confirmed
        elif decision == "approve_selected":
            if not approved_ad_sets:
                return {
                    "error": "approved_ad_sets required for partial approval",
                    "status": "error",
                }
            if user_role == "EDITOR":
                request["status"] = "escalated"
            else:
                if request["is_production"] and not production_confirmed:
                    return {
                        "status": "requires_production_confirm",
                        "message": (
                            "LIVE ADS — REAL MONEY. "
                            "Set production_confirmed=true to confirm."
                        ),
                    }
                request["status"] = "partial"
            request["approved_ad_sets"] = approved_ad_sets
            request["approved_by"] = approved_by
            request["approved_at"] = now
            request["production_confirmed"] = production_confirmed
        else:
            return {"error": f"Invalid decision: {decision}", "status": "error"}

        await self._save(request_id, tenant_id, request)

        logger.info(
            "Approval processed: id=%s, decision=%s, status=%s, by=%s",
            request_id,
            decision,
            request["status"],
            approved_by,
        )

        return {
            "status": request["status"],
            "request_id": request_id,
            "approved_ad_sets": request.get("approved_ad_sets"),
            "feedback": request.get("feedback"),
            "approved_by": approved_by,
        }

    async def get_approval_request(
        self, request_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        """Get an approval request by ID."""
        if self._redis:
            return await self._redis.get_approval_request(
                tenant_id, request_id
            )
        return self._memory_store.get(request_id)

    async def list_pending(self, tenant_id: str) -> list[dict[str, Any]]:
        """List all pending approval requests for a tenant."""
        if self._redis:
            return await self._redis.list_pending_approvals(tenant_id)
        return [
            r
            for r in self._memory_store.values()
            if r["tenant_id"] == tenant_id and r["status"] == "pending"
        ]

    async def _save(
        self, request_id: str, tenant_id: str, data: dict[str, Any]
    ):
        """Persist updated approval request."""
        if self._redis:
            await self._redis.update_approval_request(
                tenant_id, request_id, data
            )
        else:
            self._memory_store[request_id] = data
