"""HTTP client for Django ingest endpoints (intelligence_loop app)."""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class DjangoClient:
    """Posts intelligence reports to Django for persistence + RAG sync."""

    def __init__(self):
        self._timeout = httpx.Timeout(30.0, connect=10.0)

    def _headers(self, tenant_id: str | None) -> dict[str, str]:
        h = {
            "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
            "Content-Type": "application/json",
        }
        if tenant_id:
            h["X-Tenant-ID"] = str(tenant_id)
        return h

    async def get_campaign_context(
        self, tenant_id: str | None, campaign_id: str
    ) -> dict[str, Any] | None:
        url = (
            f"{settings.backend_url}/api/v1/intelligence-loop/"
            f"campaign-context/{campaign_id}/"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers(tenant_id))
                if resp.status_code >= 400:
                    logger.warning(
                        "Django campaign-context fetch failed status=%s body=%s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    return None
                return resp.json()
        except Exception as exc:
            logger.warning("Django campaign-context exception (fail-open): %s", exc)
            return None

    async def auto_trigger_rerun(
        self, tenant_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        url = (
            f"{settings.backend_url}/api/v1/intelligence-loop/auto-trigger/"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json=payload, headers=self._headers(tenant_id)
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Django auto-trigger failed status=%s body=%s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    return None
                return resp.json()
        except Exception as exc:
            logger.warning("Django auto-trigger exception (fail-open): %s", exc)
            return None

    async def create_wf2_request(
        self, tenant_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        url = (
            f"{settings.backend_url}/api/v1/intelligence-loop/"
            f"ingest/wf2-request/"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json=payload, headers=self._headers(tenant_id)
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Django wf2-request failed status=%s body=%s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    return None
                return resp.json()
        except Exception as exc:
            logger.warning("Django wf2-request exception (fail-open): %s", exc)
            return None

    async def ingest_rag_learning(
        self, tenant_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        url = (
            f"{settings.backend_url}/api/v1/intelligence-loop/"
            f"ingest/rag-learning/"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json=payload, headers=self._headers(tenant_id)
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Django rag-learning ingest failed status=%s body=%s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    return None
                return resp.json()
        except Exception as exc:
            logger.warning("Django rag-learning exception (fail-open): %s", exc)
            return None

    async def ingest_intelligence_report(
        self, tenant_id: str | None, report: dict[str, Any]
    ) -> dict[str, Any] | None:
        url = (
            f"{settings.backend_url}/api/v1/intelligence-loop/"
            f"ingest/intelligence-report/"
        )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, json=report, headers=self._headers(tenant_id)
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Django ingest failed status=%s body=%s",
                        resp.status_code,
                        resp.text[:300],
                    )
                    return None
                return resp.json()
        except Exception as exc:
            logger.warning("Django ingest exception (fail-open): %s", exc)
            return None
