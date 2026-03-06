"""Direct Vertex AI Discovery Engine adapter for RAG operations.

Mirrors the Django VertexAIAdapter pattern but uses async + per-tenant
data store resolution via TenantDataStoreResolver.
"""

import asyncio
import json
import logging
import time
from typing import Any, Optional

from app.core.config import settings
from app.rag.tenant_resolver import TenantDataStoreResolver

logger = logging.getLogger(__name__)


class VertexAIRAGAdapter:
    """Async adapter for Vertex AI Discovery Engine.

    Supports upsert, search, delete, and get operations.
    Uses run_in_executor for sync Discovery Engine SDK calls.
    Falls back to mock mode when SDK is not installed.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        default_data_store_id: Optional[str] = None,
        mock_mode: Optional[bool] = None,
        tenant_resolver: Optional[TenantDataStoreResolver] = None,
    ) -> None:
        self.project_id = project_id or settings.VERTEX_AI_PROJECT_ID
        self.location = location or settings.VERTEX_AI_LOCATION
        self.default_data_store_id = (
            default_data_store_id or settings.VERTEX_AI_DATA_STORE_ID
        )
        self.mock_mode = (
            mock_mode if mock_mode is not None else settings.VERTEX_AI_MOCK_MODE
        )
        self.tenant_resolver = tenant_resolver
        self._doc_client = None
        self._search_client = None

    def _get_doc_client(self):
        """Lazy-init the DocumentServiceClient."""
        if self.mock_mode:
            return None
        if self._doc_client is None:
            try:
                from google.cloud import discoveryengine_v1 as discoveryengine

                self._doc_client = discoveryengine.DocumentServiceClient()
            except ImportError:
                logger.warning(
                    "google-cloud-discoveryengine not installed — using mock mode"
                )
                self.mock_mode = True
                return None
        return self._doc_client

    def _get_search_client(self):
        """Lazy-init the SearchServiceClient."""
        if self.mock_mode:
            return None
        if self._search_client is None:
            try:
                from google.cloud import discoveryengine_v1 as discoveryengine

                self._search_client = discoveryengine.SearchServiceClient()
            except ImportError:
                logger.warning(
                    "google-cloud-discoveryengine not installed — using mock mode"
                )
                self.mock_mode = True
                return None
        return self._search_client

    async def _get_data_store_id(self, tenant_id: str) -> str:
        """Resolve tenant → data store ID."""
        if self.tenant_resolver:
            return await self.tenant_resolver.resolve_data_store_id(tenant_id)
        return self.default_data_store_id

    def _build_data_store_path(self, data_store_id: str) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"collections/default_collection/dataStores/{data_store_id}"
        )

    async def upsert_document(
        self,
        document_id: str,
        document_content: dict[str, Any],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Upsert a document into Vertex AI Discovery Engine.

        Uses UpdateDocumentRequest with allow_missing=True for idempotent upserts.
        """
        start = time.time()

        client = self._get_doc_client()
        if client is None:
            logger.info(
                "[MOCK] Upserting document %s for tenant %s", document_id, tenant_id
            )
            return {
                "status": "mock_completed",
                "document_id": document_id,
                "processing_time_ms": int((time.time() - start) * 1000),
            }

        data_store_id = await self._get_data_store_id(tenant_id)
        parent = self._build_data_store_path(data_store_id)

        try:
            from google.cloud import discoveryengine_v1 as discoveryengine

            # Sanitize struct_data for Vertex AI
            sanitized = self._sanitize_for_vertex(document_content)
            json_str = json.dumps(sanitized, default=str)

            branch = f"{parent}/branches/default_branch"
            document = discoveryengine.Document(
                name=f"{branch}/documents/{document_id}",
                id=document_id,
                json_data=json_str,
            )

            request = discoveryengine.UpdateDocumentRequest(
                document=document,
                allow_missing=True,
            )

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: client.update_document(request=request)
            )

            processing_ms = int((time.time() - start) * 1000)
            op_name = result.name if hasattr(result, "name") else "direct"
            logger.info(
                "Document upserted: %s, operation: %s, tenant: %s",
                document_id,
                op_name,
                tenant_id,
            )
            return {
                "status": "completed",
                "document_id": document_id,
                "processing_time_ms": processing_ms,
            }

        except Exception as exc:
            error_msg = str(exc)
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                logger.warning(
                    "Rate limit exceeded upserting %s: %s", document_id, error_msg
                )
                return {"status": "rate_limited", "error": error_msg}

            logger.error("Failed to upsert document %s: %s", document_id, error_msg)
            return {"status": "error", "error": error_msg}

    async def search(
        self,
        query: str,
        tenant_id: str = "default",
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Search Vertex AI Discovery Engine."""
        client = self._get_search_client()
        if client is None:
            logger.info("[MOCK] Search query=%s tenant=%s", query[:50], tenant_id)
            return {"results": [], "total_size": 0, "mock": True}

        data_store_id = await self._get_data_store_id(tenant_id)
        parent = self._build_data_store_path(data_store_id)

        try:
            from google.cloud import discoveryengine_v1 as discoveryengine

            serving_config = f"{parent}/servingConfigs/default_serving_config"

            request = discoveryengine.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=top_k,
            )

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: client.search(request=request)
            )

            results = []
            for result in response.results:
                doc = result.document
                doc_data = {}
                if doc.json_data:
                    try:
                        doc_data = json.loads(doc.json_data)
                    except json.JSONDecodeError:
                        doc_data = {"raw": doc.json_data}

                results.append(
                    {
                        "document_id": doc.id,
                        "text": doc_data.get("extracted_text", ""),
                        "metadata": doc_data.get("metadata", {}),
                        "document_type": doc_data.get("document_type", ""),
                    }
                )

            return {"results": results, "total_size": response.total_size}

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Search failed for tenant %s: %s", tenant_id, error_msg)
            return {"results": [], "error": error_msg}

    async def delete_document(
        self,
        document_id: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Delete a document from Vertex AI Discovery Engine."""
        client = self._get_doc_client()
        if client is None:
            logger.info(
                "[MOCK] Deleting document %s for tenant %s", document_id, tenant_id
            )
            return {"status": "mock_completed", "document_id": document_id}

        data_store_id = await self._get_data_store_id(tenant_id)
        parent = self._build_data_store_path(data_store_id)

        try:
            from google.cloud import discoveryengine_v1 as discoveryengine

            document_name = f"{parent}/branches/default_branch/documents/{document_id}"

            request = discoveryengine.DeleteDocumentRequest(name=document_name)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None, lambda: client.delete_document(request=request)
            )

            logger.info("Document deleted: %s, tenant: %s", document_id, tenant_id)
            return {"status": "completed", "document_id": document_id}

        except Exception as exc:
            error_msg = str(exc)
            if "NOT_FOUND" in error_msg or "404" in error_msg:
                return {"status": "not_found", "document_id": document_id}

            logger.error("Failed to delete document %s: %s", document_id, error_msg)
            return {"status": "error", "error": error_msg}

    async def get_document(
        self,
        document_id: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Retrieve a document from Vertex AI Discovery Engine."""
        client = self._get_doc_client()
        if client is None:
            logger.info("[MOCK] Getting document %s", document_id)
            return {"id": document_id, "mock": True}

        data_store_id = await self._get_data_store_id(tenant_id)
        parent = self._build_data_store_path(data_store_id)

        try:
            from google.cloud import discoveryengine_v1 as discoveryengine

            document_name = f"{parent}/branches/default_branch/documents/{document_id}"

            request = discoveryengine.GetDocumentRequest(name=document_name)

            loop = asyncio.get_running_loop()
            document = await loop.run_in_executor(
                None, lambda: client.get_document(request=request)
            )

            return {
                "id": document.id,
                "name": document.name,
                "json_data": document.json_data,
            }

        except Exception as exc:
            error_msg = str(exc)
            if "NOT_FOUND" in error_msg or "404" in error_msg:
                return {"error": "not_found", "document_id": document_id}

            logger.error("Failed to get document %s: %s", document_id, error_msg)
            return {"error": error_msg}

    @staticmethod
    def _sanitize_for_vertex(content: dict[str, Any]) -> dict[str, Any]:
        """Sanitize document content for Vertex AI Discovery Engine.

        Strips variable-shape fields (tables, lists, key_value_pairs) that
        cause schema-mismatch errors. The searchable text lives in
        extracted_text, so no search quality is lost.
        """
        struct_data = content.get("struct_data")
        if not isinstance(struct_data, dict):
            return content

        for key in ("tables", "lists", "key_value_pairs"):
            struct_data.pop(key, None)

        return content
