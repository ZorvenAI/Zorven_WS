"""
Callback client — sends progress and result callbacks to core-api-service.

Uses HTTP PATCH to the callback_url with X-Callback-Token authentication.
Matches the contract in ai-brand-automator/orchestration/views.py callback endpoint.
"""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class CallbackClient:
    """HTTP client for sending job progress/results to core-api-service."""

    def __init__(self, callback_token: str, timeout: float = 30.0):
        self.callback_token = callback_token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "X-Callback-Token": self.callback_token,
            "Content-Type": "application/json",
        }

    async def _patch(self, callback_url: str, payload: dict[str, Any]) -> bool:
        """
        Send a PATCH request to the callback URL.

        Returns True on success, False on failure (non-fatal).
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.patch(
                    callback_url,
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                logger.debug(
                    "Callback sent to %s: %s",
                    callback_url,
                    payload.get("status", "progress"),
                )
                return True
        except httpx.HTTPError as exc:
            logger.error(
                "Callback failed for %s: %s",
                callback_url,
                str(exc),
            )
            return False

    async def send_progress(
        self,
        callback_url: str,
        progress: dict[str, Any],
    ) -> bool:
        """Send a progress update (node status changes)."""
        return await self._patch(callback_url, {"progress": progress})

    async def send_completed(
        self,
        callback_url: str,
        result_data: dict[str, Any],
        progress: dict[str, Any],
    ) -> bool:
        """Send a completion callback with final results."""
        return await self._patch(
            callback_url,
            {
                "status": "completed",
                "progress": progress,
                "result_data": result_data,
            },
        )

    async def send_failed(
        self,
        callback_url: str,
        error_message: str,
        progress: dict[str, Any],
    ) -> bool:
        """Send a failure callback with error details."""
        return await self._patch(
            callback_url,
            {
                "status": "failed",
                "progress": progress,
                "error_message": error_message[:10000],
            },
        )

    async def send_running(
        self,
        callback_url: str,
        progress: dict[str, Any],
    ) -> bool:
        """Send a running status callback (job execution started)."""
        return await self._patch(
            callback_url,
            {
                "status": "running",
                "progress": progress,
            },
        )

    async def send_resolved_manifest(
        self,
        callback_url: str,
        manifest_id: str,
        progress: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Send a resolved manifest ID after intent routing."""
        payload: dict[str, Any] = {"resolved_manifest_id": manifest_id}
        if progress is not None:
            payload["progress"] = progress
        return await self._patch(callback_url, payload)
