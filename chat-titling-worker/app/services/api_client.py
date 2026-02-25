"""
Core API client — sends title updates back to the Django backend.

Uses HTTP PATCH to the internal title endpoint with X-Worker-Token
authentication.
"""

import logging

import httpx

logger = logging.getLogger(__name__)


class CoreApiClient:
    """HTTP client for sending title updates to the Django backend."""

    def __init__(self, base_url: str, worker_token: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.worker_token = worker_token
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a reusable AsyncClient, creating one if needed."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client. Call on shutdown."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def update_title(
        self, session_id: str, title: str, tenant_id: str
    ) -> bool:
        """
        PATCH the session title to the Django backend.

        Returns True on success, False on failure (non-fatal).
        """
        url = (
            f"{self.base_url}/api/v1/ai/internal/"
            f"title-session/{session_id}/"
        )
        headers = {
            "X-Worker-Token": self.worker_token,
            "X-Tenant-ID": tenant_id,
            "Content-Type": "application/json",
        }
        payload = {"title": title}

        try:
            client = await self._get_client()
            response = await client.patch(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.debug(
                "Title update sent for session %s: '%s'",
                session_id,
                title,
            )
            return True
        except httpx.HTTPError as exc:
            logger.error(
                "Title update failed for session %s: %s",
                session_id,
                str(exc),
            )
            return False
