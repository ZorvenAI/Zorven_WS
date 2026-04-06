"""HTTP client for service-to-service callbacks to the Django backend.

All endpoints used here are authenticated by service tokens (no JWT):
- /api/v1/optimization/callback/tick-result/  →  X-Callback-Token
- /api/v1/optimization/register/              →  X-Service-Token (or X-Callback-Token)

DRF ViewSet endpoints (e.g. /campaigns/{id}/, /recommendations/{id}/) require
JWT auth and MUST NOT be called from this client. Recommendation/action/entity
updates are bundled into the tick-result callback payload instead.
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

    def _service_headers(self, tenant_id: str = "") -> dict[str, str]:
        headers = {
            "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
            "Content-Type": "application/json",
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        return headers

    def _callback_headers(self, tenant_id: str = "") -> dict[str, str]:
        headers = {
            "X-Callback-Token": settings.CALLBACK_TOKEN,
            "Content-Type": "application/json",
        }
        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id
        return headers

    async def post_tick_result(
        self,
        tenant_id: str,
        campaign_id: str,
        tick_results: dict[str, Any],
    ) -> dict[str, Any]:
        """POST tick results to Django callback endpoint.

        Payload is flattened to match TickResultCallbackSerializer:
        tick_id, tenant_id, campaign_id, mode, performance, recommendations,
        actions, entity_updates are top-level fields.
        """
        url = f"{self._base_url}/api/v1/optimization/callback/tick-result/"

        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "tick_id": tick_results.get("tick_id", ""),
            "mode": tick_results.get("mode", "manual"),
            "campaigns_processed": tick_results.get("campaigns_processed", 0),
            "recommendations_generated": tick_results.get(
                "recommendations_generated", 0
            ),
            "auto_actions_executed": tick_results.get("auto_actions_executed", 0),
            "performance": tick_results.get("performance", {}),
            "recommendations": tick_results.get("recommendations", []),
            "actions": tick_results.get("actions", []),
            "entity_updates": tick_results.get("entity_updates", {}),
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._callback_headers(tenant_id),
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

    async def register_campaign_for_optimization(
        self,
        tenant_id: str,
        campaign_id: str = "",
        meta_campaign_id: str = "",
        campaign_name: str = "",
        meta_ad_account_id: str = "",
        objective: str = "",
        daily_budget_usd: float = 0.0,
        ad_sets: list[dict[str, Any]] | None = None,
        ads: list[dict[str, Any]] | None = None,
        sandbox_mode: bool = True,
        optimization_mode: str = "manual",
        source_job_id: str = "",
        company_id: int | None = None,
    ) -> dict[str, Any]:
        """Register a published campaign for continuous optimization.

        Calls the service-auth endpoint POST /api/v1/optimization/register/.
        """
        url = f"{self._base_url}/api/v1/optimization/register/"
        payload: dict[str, Any] = {
            "tenant_id": tenant_id,
            "company_id": company_id,
            "meta_campaign_id": meta_campaign_id or campaign_id,
            "meta_ad_account_id": meta_ad_account_id,
            "campaign_name": campaign_name,
            "objective": objective,
            "status": "active",
            "optimization_mode": optimization_mode,
            "daily_budget_usd": daily_budget_usd,
            "ad_sets": ad_sets or [],
            "ads": ads or [],
            "source_job_id": source_job_id or None,
            "sandbox_mode": sandbox_mode,
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._service_headers(tenant_id),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Campaign registration failed (HTTP %d): %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return {"error": str(exc), "status_code": exc.response.status_code}
        except Exception as exc:
            logger.error("Campaign registration failed: %s", exc)
            return {"error": str(exc)}
