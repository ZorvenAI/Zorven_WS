"""
Callback client — sends progress and result callbacks to core-api-service.

Uses HTTP PATCH to the callback_url with X-Callback-Token authentication.
Matches the contract in ai-brand-automator/orchestration/views.py callback endpoint.

Retries up to 4 times with exponential back-off (0.5 s, 1 s, 2 s) on
transient errors (5xx, connection resets, Railway DNS warm-up).  4xx errors
are considered deterministic and are never retried.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Max retries for transient connection errors (stale connections, resets,
# Railway DNS warm-up on .railway.internal hostnames).
_MAX_RETRIES = 4
_RETRY_DELAYS = [0.5, 1.0, 2.0]  # exponential back-off between attempts


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

        Retries on transport-level errors (connection resets, timeouts) and
        5xx responses.  Does NOT retry on 4xx (deterministic client errors).
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

            except httpx.HTTPStatusError as exc:
                # 4xx → non-retryable (bad request, auth, etc.)
                if exc.response.status_code < 500:
                    # Log a capped snippet of the response for diagnosis
                    # (e.g. DisallowedHost).  .content reads the full body
                    # but 4xx error pages are typically small; we slice to
                    # 512 bytes and flatten newlines for a single log line.
                    body = ""
                    if exc.response is not None:
                        raw = exc.response.content[:512]
                        body = raw.decode("utf-8", errors="replace").replace("\n", " ")
                    logger.error(
                        "Callback rejected (HTTP %d) for %s [%s]: %s " "— response: %s",
                        exc.response.status_code,
                        callback_url,
                        label,
                        exc,
                        body,
                    )
                    return False
                # 5xx → retryable
                if attempt >= _MAX_RETRIES - 1:
                    logger.error(
                        "Callback failed after %d attempts for %s " "[%s]: HTTP %d",
                        _MAX_RETRIES,
                        callback_url,
                        label,
                        exc.response.status_code,
                    )
                    return False
                logger.warning(
                    "Callback attempt %d got HTTP %d for %s [%s] " "— retrying",
                    attempt + 1,
                    exc.response.status_code,
                    callback_url,
                    label,
                )

            except Exception as exc:
                # Transport errors (connection reset, timeout, DNS, etc.)
                if attempt >= _MAX_RETRIES - 1:
                    logger.error(
                        "Callback failed after %d attempts for %s " "[%s]: %s (%s)",
                        _MAX_RETRIES,
                        callback_url,
                        label,
                        exc,
                        type(exc).__name__,
                    )
                    return False
                logger.warning(
                    "Callback attempt %d failed for %s [%s]: %s (%s) " "— retrying",
                    attempt + 1,
                    callback_url,
                    label,
                    exc,
                    type(exc).__name__,
                )

            delay = (
                _RETRY_DELAYS[attempt]
                if attempt < len(_RETRY_DELAYS)
                else _RETRY_DELAYS[-1]
            )
            await asyncio.sleep(delay)

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
