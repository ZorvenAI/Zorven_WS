"""HTTP context loader for WF1 + BPA + BPV + Company data."""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class NTAContextLoader:
    """Loads WF1, BPA, BPV, and Company context from Django backend."""

    async def load_all(
        self, tenant_id: str
    ) -> dict[str, Any]:
        """Load all contexts in parallel."""
        wf1, bpa, bpv, company = await asyncio.gather(
            self.load_wf1(tenant_id),
            self.load_bpa(tenant_id),
            self.load_bpv(tenant_id),
            self.load_company(tenant_id),
            return_exceptions=True,
        )
        return {
            "wf1": wf1 if not isinstance(wf1, Exception) else None,
            "bpa": bpa if not isinstance(bpa, Exception) else None,
            "bpv": bpv if not isinstance(bpv, Exception) else None,
            "company": company if not isinstance(company, Exception) else None,
        }

    async def load_wf1(self, tenant_id: str) -> dict[str, Any] | None:
        """Load WF1 Brand Discovery context."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/wf1-context/",
            tenant_id,
            "WF1",
        )

    async def load_bpa(self, tenant_id: str) -> dict[str, Any] | None:
        """Load BPA Brand Positioning context."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/bpa-context/",
            tenant_id,
            "BPA",
        )

    async def load_bpv(self, tenant_id: str) -> dict[str, Any] | None:
        """Load BPV Brand Personality context."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/bpv-context/",
            tenant_id,
            "BPV",
        )

    async def load_company(self, tenant_id: str) -> dict[str, Any] | None:
        """Load Company model context."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/company-context/",
            tenant_id,
            "Company",
        )

    async def _get(
        self, url: str, tenant_id: str, label: str
    ) -> dict[str, Any] | None:
        """Generic GET with service-token auth."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={
                        "X-Service-Token": settings.BACKEND_SERVICE_TOKEN,
                        "X-Tenant-ID": tenant_id,
                    },
                )
            if resp.status_code == 200:
                logger.info("%s context loaded for tenant %s", label, tenant_id)
                return resp.json()
            elif resp.status_code == 404:
                logger.info("No %s data for tenant %s", label, tenant_id)
                return None
            else:
                logger.warning(
                    "%s context load failed: %s %s",
                    label,
                    resp.status_code,
                    resp.text[:200],
                )
                return None
        except Exception as exc:
            logger.warning("%s context load error: %s", label, exc)
            return None
