"""HTTP client to fetch WF1 Brand Discovery context from Django backend.

Calls GET /api/v1/analytics/wf1-context/ with X-Service-Token and
X-Tenant-ID headers to retrieve the latest completed WF1 pipeline
result for a given tenant.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WF1ContextLoader:
    """Loads WF1 Brand Discovery data from Django backend."""

    def __init__(self, backend_url: str, service_token: str) -> None:
        self._url = f"{backend_url}/api/v1/analytics/wf1-context/"
        self._token = service_token

    async def load(self, tenant_id: str) -> dict[str, Any] | None:
        """Fetch latest WF1 context for a tenant.

        Returns None if no WF1 data is available (404).
        Raises on other HTTP errors.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    self._url,
                    headers={
                        "X-Tenant-ID": tenant_id,
                        "X-Service-Token": self._token,
                    },
                )
                if resp.status_code == 404:
                    logger.info("No WF1 data for tenant %s (404)", tenant_id)
                    return None
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "Loaded WF1 context for tenant %s: snapshot=%s",
                    tenant_id,
                    data.get("snapshot_id", "unknown"),
                )
                return data
        except httpx.HTTPStatusError as exc:
            logger.error(
                "WF1 context load failed (HTTP %d): %s",
                exc.response.status_code,
                exc,
            )
            return None
        except Exception as exc:
            logger.error("WF1 context load failed: %s", exc)
            return None
