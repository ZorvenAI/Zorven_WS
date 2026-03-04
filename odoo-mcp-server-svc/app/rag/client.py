"""RAG client — async HTTP client to rag-uploader-agent-service.

Tenant-aware with namespace isolation by tenant_id.
"""

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class RAGClient:
    """Async HTTP client for the RAG uploader agent service."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.RAG_SERVICE_URL).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def query(
        self,
        query: str,
        tenant_id: str = "default",
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Query the RAG knowledge store."""
        client = await self._get_client()
        try:
            response = await client.post(
                "/v1/query",
                json={
                    "query": query,
                    "namespace": tenant_id,
                    "top_k": top_k,
                },
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("RAG query failed: %s", exc)
            return {"results": [], "error": str(exc)}

    async def upload_document(
        self,
        content: str,
        metadata: dict[str, Any],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Upload a document to the RAG store."""
        client = await self._get_client()
        try:
            response = await client.post(
                "/v1/upload",
                json={
                    "content": content,
                    "metadata": metadata,
                    "namespace": tenant_id,
                },
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("RAG upload failed: %s", exc)
            return {"error": str(exc)}

    async def list_documents(self, tenant_id: str = "default") -> dict[str, Any]:
        """List documents in the RAG store."""
        client = await self._get_client()
        try:
            response = await client.get(
                "/v1/documents",
                params={"namespace": tenant_id},
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("RAG list failed: %s", exc)
            return {"documents": [], "error": str(exc)}

    async def get_document(
        self, doc_id: str, tenant_id: str = "default"
    ) -> dict[str, Any]:
        """Get a specific document."""
        client = await self._get_client()
        try:
            response = await client.get(
                f"/v1/documents/{doc_id}",
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("RAG get document failed: %s", exc)
            return {"error": str(exc)}

    async def delete_document(
        self, doc_id: str, tenant_id: str = "default"
    ) -> dict[str, Any]:
        """Delete a document from the RAG store."""
        client = await self._get_client()
        try:
            response = await client.delete(
                f"/v1/documents/{doc_id}",
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("RAG delete failed: %s", exc)
            return {"error": str(exc)}

    async def get_context(
        self, model: str, record_id: int, tenant_id: str = "default"
    ) -> dict[str, Any]:
        """Get RAG context for an Odoo record."""
        return await self.query(
            query=f"{model} record {record_id}",
            tenant_id=tenant_id,
        )

    async def get_stats(self, tenant_id: str = "default") -> dict[str, Any]:
        """Get RAG store statistics."""
        client = await self._get_client()
        try:
            response = await client.get(
                "/v1/stats",
                headers={"X-Tenant-ID": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.warning("RAG stats failed: %s", exc)
            return {"error": str(exc)}
