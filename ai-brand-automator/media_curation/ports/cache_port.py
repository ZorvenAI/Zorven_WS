"""
Cache Port.

Abstract interface for caching and status tracking.
Concrete implementation: RedisAdapter.

Used for:
- Tracking curation status per trace_id
- Storing tenant configurations
- Event deduplication
"""

from abc import ABC, abstractmethod
from typing import Optional, Any

from media_curation.domain.models import (
    CurationStatus,
    CurationStatusRecord,
    TenantConfig,
)


class CachePort(ABC):
    """
    Abstract interface for caching operations.

    Provides status tracking, tenant config storage, and deduplication.
    """

    # Status tracking

    @abstractmethod
    async def get_status(
        self,
        trace_id: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[CurationStatusRecord]:
        """
        Get curation status for a trace_id.

        Args:
            trace_id: The trace ID to look up
            tenant_id: Optional tenant ID for key namespacing

        Returns:
            CurationStatusRecord or None if not found
        """
        pass

    @abstractmethod
    async def set_status(
        self,
        trace_id: str,
        status: CurationStatusRecord,
        ttl_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Store curation status.

        Args:
            trace_id: The trace ID
            status: Status record to store
            ttl_seconds: Optional TTL (uses default if not provided)
            tenant_id: Optional tenant ID for key namespacing
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        trace_id: str,
        status: CurationStatus,
        tenant_id: Optional[str] = None,
        **updates: Any,
    ) -> None:
        """
        Update status fields for existing record.

        Args:
            trace_id: The trace ID
            status: New status value
            tenant_id: Optional tenant ID for key namespacing
            **updates: Additional fields to update
        """
        pass

    # Tenant configuration

    @abstractmethod
    async def get_tenant_config(self, tenant_id: str) -> Optional[TenantConfig]:
        """
        Get tenant-specific configuration.

        Args:
            tenant_id: The tenant ID

        Returns:
            TenantConfig or None if not found
        """
        pass

    @abstractmethod
    async def set_tenant_config(
        self,
        tenant_id: str,
        config: TenantConfig,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Store tenant configuration.

        Args:
            tenant_id: The tenant ID
            config: Configuration to store
            ttl_seconds: Optional TTL
        """
        pass

    # Deduplication

    @abstractmethod
    async def is_duplicate(
        self,
        event_id: str,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """
        Check if event has already been processed.

        Args:
            event_id: The event ID to check
            tenant_id: Optional tenant ID for key namespacing

        Returns:
            True if duplicate, False otherwise
        """
        pass

    @abstractmethod
    async def mark_processed(
        self,
        event_id: str,
        ttl_seconds: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Mark event as processed for deduplication.

        Args:
            event_id: The event ID
            ttl_seconds: How long to remember (default: 7 days)
            tenant_id: Optional tenant ID for key namespacing
        """
        pass

    # Health check

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if cache service is available."""
        pass
