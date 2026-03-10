"""RAG client — retrieves context from tenant's RAG store."""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class RAGClient:
    """Retrieves context from RAG store to enrich agent reasoning."""

    def __init__(
        self,
        service_url: str = "http://localhost:8070",
        enabled: bool = False,
    ) -> None:
        self.service_url = service_url.rstrip("/")
        self.enabled = enabled
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Return an HTTP client, creating one if needed."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.service_url,
                timeout=30.0,
            )
        return self._client

    async def get_context(
        self,
        query: str,
        tenant_id: str,
        data_store_id: str = "",
    ) -> str:
        """Query RAG store and return relevant context.

        Returns empty string on failure (fail-open).
        """
        if not self.enabled:
            return ""

        if not data_store_id:
            return ""

        try:
            client = await self._get_client()
            response = await client.post(
                "/v1/query",
                json={
                    "query": query,
                    "data_store_id": data_store_id,
                },
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()

            data = response.json()
            context = data.get("context", "")
            if context:
                logger.info(
                    "RAG context retrieved (%d chars) for tenant %s",
                    len(context),
                    tenant_id,
                )
            return context

        except Exception as exc:
            logger.warning("RAG context retrieval failed: %s", exc)
            return ""

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
