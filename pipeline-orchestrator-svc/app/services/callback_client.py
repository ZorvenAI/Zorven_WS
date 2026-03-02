"""
Callback client — sends progress and result callbacks to core-api-service.

Uses HTTP PATCH to the callback_url with X-Callback-Token authentication.
Matches the contract in ai-brand-automator/orchestration/views.py callback endpoint.

Retries once on connection errors (stale connections from cloud load balancers)
using a fresh httpx client on the retry attempt.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Max retries for transient connection errors (stale connections, resets)
_MAX_RETRIES = 2
_RETRY_DELAY = 0.5  # seconds


class CallbackClient:
    """HTTP client for sending job progress/results to core-api-service.

    Creates a fresh httpx.AsyncClient per request to avoid stale connection
    issues when callbacks route through cloud load balancers (Railway, etc.).
    """

    def __init__(self, callback_token: str, timeout: float = 30.0):
        self.callback_token = callback_token
        self.timeout = timeout

    async def close(self) -> None:
        """No-op — clients are created per-request now."""

    def _headers(self) -> dict[str, str]:
        return {
            "X-Callback-Token": self.callback_token,
            "Content-Type": "application/json",
        }

    async def _patch(self, callback_url: str, payload: dict[str, Any]) -> bool:
        """
        Send a PATCH request to the callback URL.

        Retries once on connection/transport errors using a fresh client.
        Returns True on success, False on failure (non-fatal).
        """
        label = payload.get("status") or next(
            (k for k in ("resolved_manifest_id", "progress") if k in payload),
            "unknown",
        )

        for attempt in range(_MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.patch(
                        callback_url,
                        json=payload,
                        headers=self._headers(),
                    )
                    response.raise_for_status()

                logger.info(
                    "Callback sent: %s (HTTP %d, attempt %d)",
                    label,
                    response.status_code,
                    attempt + 1,
                )
                return True

            except Exception as exc:
                is_last = attempt >= _MAX_RETRIES - 1
                if is_last:
                    logger.error(
                        "Callback failed after %d attempts for %s [%s]: %s (%s)",
                        _MAX_RETRIES,
                        callback_url,
                        label,
                        exc,
                        type(exc).__name__,
                    )
                    return False

                logger.warning(
                    "Callback attempt %d failed for %s [%s]: %s (%s) — retrying",
                    attempt + 1,
                    callback_url,
                    label,
                    exc,
                    type(exc).__name__,
                )
                await asyncio.sleep(_RETRY_DELAY)

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
