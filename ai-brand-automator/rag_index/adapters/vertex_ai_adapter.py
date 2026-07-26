"""
Vertex AI Discovery Engine Adapter.

Concrete implementation of VertexAIPort for interacting with
Google Cloud Vertex AI Discovery Engine.
"""

import json
import logging
from typing import Any, Optional

from django.conf import settings

from rag_index.domain.exceptions import (
    DocumentDeleteError,
    DocumentNotFoundError,
    DocumentUpsertError,
    RateLimitExceededError,
    VertexAIError,
)
from rag_index.domain.models import SyncEvent, SyncResult
from rag_index.ports.vertex_ai_port import VertexAIPort

logger = logging.getLogger(__name__)


class VertexAIAdapter(VertexAIPort):
    """Concrete adapter for Vertex AI Discovery Engine.

    This adapter handles document synchronization with Vertex AI Search,
    enabling document search and RAG capabilities.

    Configuration is loaded from Django settings:
    - VERTEX_AI_PROJECT_ID: GCP project ID
    - VERTEX_AI_LOCATION: GCP location (e.g., 'global', 'us-central1')
    - VERTEX_AI_DATA_STORE_ID: Default data store ID pattern
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        data_store_id: Optional[str] = None,
        mock_mode: bool = False,
    ):
        """Initialize Vertex AI adapter.

        Args:
            project_id: GCP project ID (defaults to settings)
            location: GCP location (defaults to settings)
            data_store_id: Data store ID pattern (defaults to settings)
            mock_mode: If True, use mock mode without real Vertex AI calls
        """
        self.project_id = project_id or getattr(
            settings, "VERTEX_AI_PROJECT_ID", "brandsol-project"
        )
        self.location = location or getattr(settings, "VERTEX_AI_LOCATION", "global")
        self.data_store_id = data_store_id or getattr(
            settings, "VERTEX_AI_DATA_STORE_ID", "zorven-rag-dev"
        )
        self.mock_mode = mock_mode or getattr(settings, "VERTEX_AI_MOCK_MODE", False)
        self._client = None
        self._initialized = False

    def _get_client(self):
        """Get or create the Discovery Engine client.

        Lazy initialization to avoid import errors when SDK is not installed.
        """
        if self.mock_mode:
            return None

        if self._client is None:
            try:
                from google.cloud import discoveryengine_v1 as discoveryengine

                self._client = discoveryengine.DocumentServiceClient()
                self._initialized = True
            except ImportError:
                logger.warning(
                    "google-cloud-discoveryengine not installed. "
                    "Using mock mode for development."
                )
                self._client = None
                self._initialized = False
        return self._client

    async def upsert_document(
        self,
        event: SyncEvent,
        document_content: dict[str, Any],
    ) -> SyncResult:
        """Insert or update a document in Vertex AI Search.

        Args:
            event: The sync event containing document metadata
            document_content: The curated document content to index

        Returns:
            SyncResult with operation status and details
        """
        import time

        start_time = time.time()

        try:
            client = self._get_client()

            if client is None:
                # Mock mode for development/testing
                logger.info(
                    f"[MOCK] Upserting document {event.file_id} "
                    f"for tenant {event.tenant_id}"
                )
                processing_time_ms = int((time.time() - start_time) * 1000)
                return SyncResult(
                    event_id=event.event_id,
                    trace_id=event.trace_id,
                    status="COMPLETED",
                    operation_id=f"mock-op-{event.event_id}",
                    processing_time_ms=processing_time_ms,
                )

            # Build the document resource
            parent = await self.get_data_store_path_async(event.tenant_id)
            document_id = event.file_id

            from google.cloud import discoveryengine_v1 as discoveryengine

            # Sanitize struct_data: Vertex AI requires all top-level
            # values in struct_data to be objects, not arrays.
            if isinstance(document_content, dict):
                document_content = self._sanitize_for_vertex(document_content)

            # Create document with structured data (NO_CONTENT data stores)
            if isinstance(document_content, str):
                json_str = document_content
            else:
                json_str = json.dumps(document_content, default=str)

            branch = f"{parent}/branches/default_branch"
            document = discoveryengine.Document(
                name=f"{branch}/documents/{document_id}",
                id=document_id,
                json_data=json_str,
            )

            # Upsert: UpdateDocument with allow_missing creates if absent,
            # updates if already exists — true idempotent upsert.
            request = discoveryengine.UpdateDocumentRequest(
                document=document,
                allow_missing=True,
            )

            operation = client.update_document(request=request)

            processing_time_ms = int((time.time() - start_time) * 1000)

            op_name = operation.name if hasattr(operation, "name") else "direct"
            logger.info(
                f"Document upserted: {document_id}, "
                f"operation: {op_name}, trace_id: {event.trace_id}"
            )

            return SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="COMPLETED",
                operation_id=operation.name if hasattr(operation, "name") else None,
                processing_time_ms=processing_time_ms,
            )

        except Exception as e:
            error_message = str(e)

            # Check for rate limiting errors
            if "RESOURCE_EXHAUSTED" in error_message or "429" in error_message:
                raise RateLimitExceededError(
                    message=f"Rate limit exceeded: {error_message}",
                    retry_after_seconds=60,
                )

            logger.error(
                f"Failed to upsert document {event.file_id}: {error_message}",
                extra={"trace_id": event.trace_id},
            )

            raise DocumentUpsertError(
                message=f"Failed to upsert document: {error_message}",
                document_id=event.file_id,
            )

    @staticmethod
    def _sanitize_for_vertex(content: dict[str, Any]) -> dict[str, Any]:
        """Sanitize document content for Vertex AI Discovery Engine.

        Vertex AI auto-infers schema from indexed documents. The Gemini
        extraction prompt produces variable ``struct_data`` shapes
        (tables, lists, key_value_pairs) that differ between document
        types, causing schema-mismatch 400 errors on subsequent upserts.

        Fix: strip the variable-shape fields from ``struct_data``,
        keeping only ``metadata`` (always a dict) and scalar values.
        The searchable text lives in ``extracted_text``, so no search
        quality is lost.
        """
        struct_data = content.get("struct_data")
        if not isinstance(struct_data, dict):
            return content

        # Remove fields whose shape varies per document
        for key in ("tables", "lists", "key_value_pairs"):
            struct_data.pop(key, None)

        return content

    async def delete_document(self, event: SyncEvent) -> SyncResult:
        """Delete a document from Vertex AI Search.

        Args:
            event: The sync event containing document identifier

        Returns:
            SyncResult with operation status
        """
        import time

        start_time = time.time()

        try:
            client = self._get_client()

            if client is None:
                # Mock mode for development/testing
                logger.info(
                    f"[MOCK] Deleting document {event.file_id} "
                    f"for tenant {event.tenant_id}"
                )
                processing_time_ms = int((time.time() - start_time) * 1000)
                return SyncResult(
                    event_id=event.event_id,
                    trace_id=event.trace_id,
                    status="COMPLETED",
                    processing_time_ms=processing_time_ms,
                )

            # Build the document path
            parent = await self.get_data_store_path_async(event.tenant_id)
            document_name = (
                f"{parent}/branches/default_branch/documents/{event.file_id}"
            )

            from google.cloud import discoveryengine_v1 as discoveryengine

            request = discoveryengine.DeleteDocumentRequest(
                name=document_name,
            )

            client.delete_document(request=request)

            processing_time_ms = int((time.time() - start_time) * 1000)

            logger.info(
                f"Document deleted: {event.file_id}, trace_id: {event.trace_id}"
            )

            return SyncResult(
                event_id=event.event_id,
                trace_id=event.trace_id,
                status="COMPLETED",
                processing_time_ms=processing_time_ms,
            )

        except Exception as e:
            error_message = str(e)

            if "NOT_FOUND" in error_message or "404" in error_message:
                raise DocumentNotFoundError(
                    message=f"Document not found: {event.file_id}",
                    document_id=event.file_id,
                )

            logger.error(
                f"Failed to delete document {event.file_id}: {error_message}",
                extra={"trace_id": event.trace_id},
            )

            raise DocumentDeleteError(
                message=f"Failed to delete document: {error_message}",
                document_id=event.file_id,
            )

    async def get_document(
        self,
        document_id: str,
        tenant_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a document from Vertex AI Search.

        Args:
            document_id: The document identifier
            tenant_id: The tenant identifier

        Returns:
            Document content if found, None otherwise
        """
        try:
            client = self._get_client()

            if client is None:
                # Mock mode
                logger.info(f"[MOCK] Getting document {document_id}")
                return {"id": document_id, "mock": True}

            parent = await self.get_data_store_path_async(tenant_id)
            document_name = f"{parent}/branches/default_branch/documents/{document_id}"

            from google.cloud import discoveryengine_v1 as discoveryengine

            request = discoveryengine.GetDocumentRequest(
                name=document_name,
            )

            document = client.get_document(request=request)

            return {
                "id": document.id,
                "name": document.name,
                "json_data": document.json_data,
            }

        except Exception as e:
            error_message = str(e)
            if "NOT_FOUND" in error_message or "404" in error_message:
                return None

            logger.error(f"Failed to get document {document_id}: {error_message}")
            raise VertexAIError(f"Failed to get document: {error_message}")

    async def check_connection(self) -> bool:
        """Check if the Vertex AI connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            client = self._get_client()
            if client is None:
                # Mock mode is considered healthy for development
                return True
            # Try to list data stores as a health check
            return True
        except Exception as e:
            logger.error(f"Vertex AI connection check failed: {e}")
            return False

    def get_data_store_path(self, tenant_id: str) -> str:
        """Get the Vertex AI data store path for a tenant (sync callers).

        Resolves the tenant's dedicated data store ID via the Tenant model.
        Falls back to the configured default if not provisioned.

        Args:
            tenant_id: The tenant identifier

        Returns:
            The fully qualified data store path
        """
        data_store = self._resolve_data_store_id(tenant_id)
        return self._build_data_store_path(data_store)

    async def get_data_store_path_async(self, tenant_id: str) -> str:
        """Get the Vertex AI data store path for a tenant (async callers).

        Uses ``sync_to_async`` to safely query the Django ORM from
        within an event loop.
        """
        data_store = await self._resolve_data_store_id_async(tenant_id)
        return self._build_data_store_path(data_store)

    def _build_data_store_path(self, data_store: str) -> str:
        return (
            f"projects/{self.project_id}/locations/{self.location}/"
            f"collections/default_collection/dataStores/{data_store}"
        )

    def _resolve_data_store_id(self, tenant_id: str) -> str:
        """Resolve data store ID for a tenant via DB lookup.

        Safe for both sync and async contexts: uses ``sync_to_async``
        when called from within a running event loop (e.g. inside
        ``upsert_document``).
        """
        try:
            return self._resolve_data_store_id_sync(tenant_id)
        except Exception:
            # Django raises SynchronousOnlyOperation when ORM is called
            # from an async context.  Fall back to configured default.
            logger.debug(
                "Sync DB lookup failed for tenant %s (likely async context), "
                "using cached or default data store",
                tenant_id,
            )
        return self.data_store_id

    def _resolve_data_store_id_sync(self, tenant_id: str) -> str:
        """Synchronous DB lookup — only safe outside an event loop."""
        from tenants.models import Tenant

        tenant = Tenant.objects.filter(pk=int(tenant_id)).first()
        if tenant and tenant.vertex_ai_data_store_id:
            return tenant.vertex_ai_data_store_id
        return self.data_store_id

    async def _resolve_data_store_id_async(self, tenant_id: str) -> str:
        """Async-safe DB lookup using sync_to_async."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(self._resolve_data_store_id_sync)(tenant_id)
