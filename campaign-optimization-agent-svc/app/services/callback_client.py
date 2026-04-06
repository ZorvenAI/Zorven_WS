"""HTTP client for callbacks to Django backend.

Methods:
- post_tick_result: POST tick results to Django
- update_campaign_status: PATCH campaign registry
- update_recommendation_status: PATCH recommendation status
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class CallbackClient:
    """HTTP client for callbacks to Django backend."""

    def __init__(self):
        self._base_url = settings.backend_url
        self._headers = {
            "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
            "Content-Type": "application/json",
        }

    async def post_tick_result(
        self,
        tenant_id: str,
        campaign_id: str,
        tick_results: dict[str, Any],
    ) -> dict[str, Any]:
        """POST tick results to Django callback endpoint.

        Args:
            tenant_id: Tenant identifier.
            campaign_id: Campaign identifier.
            tick_results: Full tick results payload.

        Returns:
            Response data from Django, or error dict.
        """
        url = (
            f"{self._base_url}/api/v1/optimization"
            f"/callback/tick-result/"
        )
        headers = {**self._headers, "X-Tenant-ID": tenant_id}
        payload = {
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "tick_results": tick_results,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    url, json=payload, headers=headers
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Tick result callback failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return {"error": str(exc), "status_code": exc.response.status_code}
        except Exception as exc:
            logger.error("Tick result callback failed: %s", exc)
            return {"error": str(exc)}

    async def update_campaign_status(
        self,
        campaign_id: str,
        status: str,
        ad_sets: list[dict[str, Any]] | None = None,
        ads: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """PATCH campaign registry in Django.

        Args:
            campaign_id: Campaign identifier.
            status: New campaign status.
            ad_sets: Updated ad set data.
            ads: Updated ad data.

        Returns:
            Response data from Django, or error dict.
        """
        url = (
            f"{self._base_url}/api/v1/optimization"
            f"/campaigns/{campaign_id}/"
        )
        payload: dict[str, Any] = {"status": status}
        if ad_sets is not None:
            payload["ad_sets"] = ad_sets
        if ads is not None:
            payload["ads"] = ads
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.patch(
                    url, json=payload, headers=self._headers
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Campaign status update failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return {"error": str(exc), "status_code": exc.response.status_code}
        except Exception as exc:
            logger.error("Campaign status update failed: %s", exc)
            return {"error": str(exc)}

    async def update_recommendation_status(
        self,
        recommendation_id: str,
        status: str,
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """PATCH recommendation status in Django.

        Args:
            recommendation_id: Recommendation identifier.
            status: New recommendation status.
            execution_result: Execution result data.

        Returns:
            Response data from Django, or error dict.
        """
        url = (
            f"{self._base_url}/api/v1/optimization"
            f"/recommendations/{recommendation_id}/"
        )
        payload: dict[str, Any] = {"status": status}
        if execution_result is not None:
            payload["execution_result"] = execution_result
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.patch(
                    url, json=payload, headers=self._headers
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Recommendation status update failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return {"error": str(exc), "status_code": exc.response.status_code}
        except Exception as exc:
            logger.error("Recommendation status update failed: %s", exc)
            return {"error": str(exc)}
