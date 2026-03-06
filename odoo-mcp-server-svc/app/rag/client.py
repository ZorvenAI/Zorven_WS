"""RAG client — facade for Vertex AI (direct) or HTTP fallback.

When a VertexAIRAGAdapter is injected, delegates directly to Vertex AI.
Otherwise falls back to HTTP calls to rag-uploader-agent-service.
"""

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class RAGClient:
    """RAG facade: Vertex AI adapter (preferred) → HTTP fallback."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        vertex_adapter: Optional[Any] = None,
    ) -> None:
        self.base_url = (base_url or settings.RAG_SERVICE_URL).rstrip("/")
        self.vertex_adapter = vertex_adapter
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def _use_vertex(self) -> bool:
        return self.vertex_adapter is not None

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
        if self._use_vertex:
            return await self.vertex_adapter.search(
                query=query, tenant_id=tenant_id, top_k=top_k
            )

        # HTTP fallback
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
        content: Any,
        metadata: dict[str, Any],
        tenant_id: str = "default",
        doc_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Upload/upsert a document to the RAG store."""
        if self._use_vertex:
            # Build document content in the expected format
            if isinstance(content, dict):
                document_content = content
            else:
                document_content = {
                    "document_type": metadata.get("document_type", "unknown"),
                    "metadata": metadata,
                    "extracted_text": str(content),
                }

            document_id = doc_id or self._generate_doc_id(metadata)
            return await self.vertex_adapter.upsert_document(
                document_id=document_id,
                document_content=document_content,
                tenant_id=tenant_id,
            )

        # HTTP fallback
        client = await self._get_client()
        try:
            response = await client.post(
                "/v1/upload",
                json={
                    "content": content if isinstance(content, str) else str(content),
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
        if self._use_vertex:
            # Vertex AI doesn't have a direct list API for unstructured stores
            return {"documents": [], "note": "List not supported via Vertex AI direct"}

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
        if self._use_vertex:
            return await self.vertex_adapter.get_document(
                document_id=doc_id, tenant_id=tenant_id
            )

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
        if self._use_vertex:
            return await self.vertex_adapter.delete_document(
                document_id=doc_id, tenant_id=tenant_id
            )

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
        if self._use_vertex:
            return {"backend": "vertex_ai", "tenant_id": tenant_id}

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

    @staticmethod
    def _generate_doc_id(metadata: dict[str, Any]) -> str:
        """Generate a deterministic document ID from metadata."""
        source = metadata.get("source", "unknown")
        model = metadata.get("model", "")
        record_id = metadata.get("record_id", "")

        if source == "odoo" and model and record_id:
            model_underscore = model.replace(".", "_")
            return f"odoo-{model_underscore}-{record_id}"

        # Fallback
        import hashlib

        content_hash = hashlib.md5(str(metadata).encode()).hexdigest()[:12]
        return f"{source}-{content_hash}"
