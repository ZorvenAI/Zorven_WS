"""HTTP context loader for WF1 + WF2 + Company + BAA + Odoo + RAG data."""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class CAAContextLoader:
    """Loads WF1, WF2 chain, Company, BAA, Odoo, and RAG context."""

    async def load_all(self, tenant_id: str) -> dict[str, Any]:
        """Load all contexts in parallel (7 calls)."""
        wf1, bpa, bpv_nta_bsa, company, baa, odoo, rag = await asyncio.gather(
            self.load_wf1(tenant_id),
            self.load_bpa(tenant_id),
            self.load_wf2_chain(tenant_id),
            self.load_company(tenant_id),
            self.load_baa(tenant_id),
            self.load_odoo(tenant_id),
            self.load_rag_learnings(tenant_id),
            return_exceptions=True,
        )
        return {
            "wf1": wf1 if not isinstance(wf1, Exception) else None,
            "bpa": bpa if not isinstance(bpa, Exception) else None,
            "wf2_chain": (
                bpv_nta_bsa if not isinstance(bpv_nta_bsa, Exception) else None
            ),
            "company": (company if not isinstance(company, Exception) else None),
            "baa": baa if not isinstance(baa, Exception) else None,
            "odoo": odoo if not isinstance(odoo, Exception) else None,
            "rag": rag if not isinstance(rag, Exception) else None,
        }

    async def load_wf1(self, tenant_id: str) -> dict[str, Any] | None:
        """Load WF1 Brand Discovery context (APA+CIA required)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/wf1-context/",
            tenant_id,
            "WF1",
        )

    async def load_bpa(self, tenant_id: str) -> dict[str, Any] | None:
        """Load BPA Brand Positioning context (required)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/bpa-context/",
            tenant_id,
            "BPA",
        )

    async def load_wf2_chain(self, tenant_id: str) -> dict[str, Any] | None:
        """Load WF2 chain context (BPV+NTA+BSA — optional enrichment)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/wf2-context/",
            tenant_id,
            "WF2-chain",
        )

    async def load_company(self, tenant_id: str) -> dict[str, Any] | None:
        """Load Company model context (required)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/company-context/",
            tenant_id,
            "Company",
        )

    async def load_baa(self, tenant_id: str) -> dict[str, Any] | None:
        """Load BAA Brand Architecture context (optional)."""
        return await self._get(
            f"{settings.BACKEND_URL}/api/v1/analytics/baa-context/",
            tenant_id,
            "BAA",
        )

    async def load_odoo(self, tenant_id: str) -> dict[str, Any] | None:
        """Load Odoo CRM customer data (optional).

        Returns None when ODOO_MCP_URL is not configured.
        """
        if not settings.ODOO_MCP_URL:
            logger.info("Odoo not configured, skipping customer data load")
            return None
        try:
            url = f"{settings.ODOO_MCP_URL}/api/v1/customers/segments"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={
                        "X-Tenant-ID": tenant_id,
                    },
                )
            if resp.status_code == 200:
                logger.info("Odoo customer data loaded for tenant %s", tenant_id)
                return resp.json()
            else:
                logger.info("Odoo customer data unavailable: %s", resp.status_code)
                return None
        except Exception as exc:
            logger.warning("Odoo customer data load error: %s", exc)
            return None

    async def load_rag_learnings(self, tenant_id: str) -> dict[str, Any] | None:
        """Load prior campaign learnings from RAG (optional).

        Returns None when RAG_DATA_STORE_ID is not configured
        or no prior campaigns exist.
        """
        if not settings.RAG_DATA_STORE_ID:
            logger.info("RAG not configured, skipping campaign learnings")
            return None
        try:
            # Vertex AI RAG search for prior campaign learnings
            from google.cloud import discoveryengine_v1 as discoveryengine

            client = discoveryengine.SearchServiceAsyncClient()
            serving_config = (
                f"projects/{settings.GCS_PROJECT_ID}"
                f"/locations/global"
                f"/collections/default_collection"
                f"/dataStores/{settings.RAG_DATA_STORE_ID}"
                f"/servingConfigs/default_serving_config"
            )
            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=f"campaign learnings tenant:{tenant_id}",
                page_size=10,
            )
            response = await client.search(request=request)
            learnings = []
            async for result in response:
                doc = result.document
                learnings.append(
                    {
                        "id": doc.id,
                        "data": dict(doc.struct_data) if doc.struct_data else {},
                    }
                )
            if learnings:
                logger.info(
                    "RAG learnings loaded: %d results for tenant %s",
                    len(learnings),
                    tenant_id,
                )
                return {"learnings": learnings}
            logger.info(
                "No RAG learnings found for tenant %s (first campaign)",
                tenant_id,
            )
            return None
        except Exception as exc:
            logger.warning("RAG learnings load error: %s", exc)
            return None

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
