"""HTTP client to fetch WF1, BPA, and Company context from Django backend.

BAA requires ALL three contexts:
- GET /api/v1/analytics/wf1-context/   — WF1 Brand Discovery results
- GET /api/v1/analytics/bpa-context/   — BPA Brand Positioning results
- GET /api/v1/analytics/company-context/ — Company model + product portfolio
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class BAAContextLoader:
    """Loads WF1, BPA, and Company context from Django backend."""

    def __init__(self, backend_url: str, service_token: str) -> None:
        self._wf1_url = f"{backend_url}/api/v1/analytics/wf1-context/"
        self._bpa_url = f"{backend_url}/api/v1/analytics/bpa-context/"
        self._company_url = f"{backend_url}/api/v1/analytics/company-context/"
        self._token = service_token

    async def load_wf1(self, tenant_id: str) -> dict[str, Any] | None:
        """Fetch latest WF1 context for a tenant.

        Returns None if no WF1 data is available (404).
        Re-raises on non-404 HTTP errors.
        Returns None on network errors (fail-open).
        """
        return await self._fetch(self._wf1_url, tenant_id, "WF1")

    async def load_bpa(self, tenant_id: str) -> dict[str, Any] | None:
        """Fetch latest BPA positioning context for a tenant.

        Returns None if no BPA data is available (404).
        """
        return await self._fetch(self._bpa_url, tenant_id, "BPA")

    async def load_company(self, tenant_id: str) -> dict[str, Any] | None:
        """Fetch Company model + product portfolio for a tenant.

        Returns None if no Company data is available (404).
        """
        return await self._fetch(self._company_url, tenant_id, "Company")

    async def load_all(self, tenant_id: str) -> dict[str, Any]:
        """Load all contexts in parallel. Returns merged dict.

        Each context is None if unavailable or on error.
        """
        wf1, bpa, company = await asyncio.gather(
            self.load_wf1(tenant_id),
            self.load_bpa(tenant_id),
            self.load_company(tenant_id),
            return_exceptions=True,
        )
        return {
            "wf1": wf1 if not isinstance(wf1, Exception) else None,
            "bpa": bpa if not isinstance(bpa, Exception) else None,
            "company": company if not isinstance(company, Exception) else None,
        }

    async def _fetch(
        self, url: str, tenant_id: str, label: str
    ) -> dict[str, Any] | None:
        """Generic fetch with error handling."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={
                        "X-Tenant-ID": tenant_id,
                        "X-Service-Token": self._token,
                    },
                )
                if resp.status_code == 404:
                    logger.info("No %s data for tenant %s (404)", label, tenant_id)
                    return None
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "Loaded %s context for tenant %s",
                    label,
                    tenant_id,
                )
                return data
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:
            logger.error("%s context load failed: %s", label, exc)
            return None
