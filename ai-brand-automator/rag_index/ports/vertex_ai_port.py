"""
Vertex AI Discovery Engine Port.

Abstract interface for interacting with Google Cloud Vertex AI
Discovery Engine (formerly known as Enterprise Search).
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from rag_index.domain.models import SyncEvent, SyncResult


class VertexAIPort(ABC):
    """Abstract interface for Vertex AI Discovery Engine operations.

    This port defines the contract for syncing documents to Vertex AI Search,
    enabling document search and RAG capabilities.
    """

    @abstractmethod
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

        Raises:
            DocumentUpsertError: If the upsert operation fails
            RateLimitExceededError: If rate limit is exceeded
        """

    @abstractmethod
    async def delete_document(
        self,
        event: SyncEvent,
    ) -> SyncResult:
        """Delete a document from Vertex AI Search.

        Args:
            event: The sync event containing document identifier

        Returns:
            SyncResult with operation status

        Raises:
            DocumentDeleteError: If the delete operation fails
            DocumentNotFoundError: If document doesn't exist
        """

    @abstractmethod
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

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the Vertex AI connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """

    @abstractmethod
    def get_data_store_path(self, tenant_id: str) -> str:
        """Get the Vertex AI data store path for a tenant.

        Args:
            tenant_id: The tenant identifier

        Returns:
            The fully qualified data store path
        """
