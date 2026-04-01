"""HTTP context loader for CAA + WF1 + WF2 + Company data."""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class CGAContextLoader:
    """Loads CAA blueprint, WF1, WF2, and Company context from Django backend."""

    async def load_all(
        self,
        tenant_id: str,
        previous_outputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Load all contexts in parallel.

        CAA blueprint is first extracted from previous_outputs (passed by
        the orchestrator when CGA runs after CAA in the same pipeline).
        Falls back to Django analytics context endpoint.
        """
        caa_from_prev = self._extract_caa_from_previous(previous_outputs)

        results = await asyncio.gather(
            self.load_wf1(tenant_id),
            self.load_bpa(tenant_id),
            self.load_bpv(tenant_id),
            self.load_nta(tenant_id),
            self.load_bsa(tenant_id),
            self.load_company(tenant_id),
            self.load_caa(tenant_id) if not caa_from_prev else _noop(),
            return_exceptions=True,
        )

        wf1, bpa, bpv, nta, bsa, company, caa_api = results

        caa = caa_from_prev or (caa_api if not isinstance(caa_api, Exception) else None)

        return {
            "caa": caa,
            "wf1": wf1 if not isinstance(wf1, Exception) else None,
            "bpa": bpa if not isinstance(bpa, Exception) else None,
            "bpv": bpv if not isinstance(bpv, Exception) else None,
            "nta": nta if not isinstance(nta, Exception) else None,
            "bsa": bsa if not isinstance(bsa, Exception) else None,
            "company": company if not isinstance(company, Exception) else None,
        }

    def _extract_caa_from_previous(
        self, previous_outputs: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Extract CAA blueprint from orchestrator previous_outputs."""
        if not previous_outputs:
            return None
        for node_id, output in previous_outputs.items():
            if isinstance(output, dict) and (
                "blueprint" in output
                or "campaign_blueprint" in output
                or "funnel_map" in output
                or "creative_briefs" in output
            ):
                logger.info(
                    "CAA blueprint found in previous_outputs (node: %s)", node_id
                )
                return output
        return None

    async def load_wf1(self, tenant_id: str) -> dict[str, Any] | None:
        """Load WF1 Brand Discovery context (APA personas)."""
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
        """Load BPV Brand Personality context (voice + archetype)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/bpv-context/",
            tenant_id,
            "BPV",
        )

    async def load_nta(self, tenant_id: str) -> dict[str, Any] | None:
        """Load NTA Brand Naming context (name + tagline)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/nta-context/",
            tenant_id,
            "NTA",
        )

    async def load_bsa(self, tenant_id: str) -> dict[str, Any] | None:
        """Load BSA Brand Story context (story arcs, optional)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/bsa-context/",
            tenant_id,
            "BSA",
        )

    async def load_company(self, tenant_id: str) -> dict[str, Any] | None:
        """Load Company model context (colors, logo, industry)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/company-context/",
            tenant_id,
            "Company",
        )

    async def load_caa(self, tenant_id: str) -> dict[str, Any] | None:
        """Load CAA Campaign Architecture context from analytics."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/caa-context/",
            tenant_id,
            "CAA",
        )

    async def _get(self, url: str, tenant_id: str, label: str) -> dict[str, Any] | None:
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


async def _noop() -> None:
    """No-op coroutine for gather when context already resolved."""
    return None
