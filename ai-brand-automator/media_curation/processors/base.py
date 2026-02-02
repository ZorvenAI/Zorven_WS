"""
Base Content Processor.

Abstract base class implementing the Strategy pattern for content processing.
Concrete implementations handle specific content types.
"""

from abc import ABC, abstractmethod
import logging
from typing import Optional
from datetime import datetime

from media_curation.domain.models import (
    CurationEvent,
    ProcessorResult,
    TenantConfig,
    ContentType,
)
from media_curation.domain.exceptions import CurationError, NonRetryableError


logger = logging.getLogger(__name__)


class BaseProcessor(ABC):
    """
    Abstract base class for content processors.

    Implements common functionality and defines the processing interface.
    Subclasses must implement:
    - supported_mime_types property
    - _process_content method
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the processor.

        Args:
            config: Optional processor-specific configuration
        """
        self.config = config or {}
        self._initialized = False

    @property
    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """
        Return list of MIME types this processor supports.

        Wildcard patterns like "video/*" are supported.
        """
        pass

    @property
    @abstractmethod
    def content_type(self) -> ContentType:
        """Return the ContentType this processor handles."""
        pass

    @property
    def name(self) -> str:
        """Return processor name for logging."""
        return self.__class__.__name__

    def supports(self, mime_type: str) -> bool:
        """
        Check if this processor supports the given MIME type.

        Args:
            mime_type: MIME type to check (e.g., "video/mp4")

        Returns:
            True if supported
        """
        for supported in self.supported_mime_types:
            if supported.endswith("/*"):
                prefix = supported[:-1]
                if mime_type.startswith(prefix):
                    return True
            elif supported == mime_type:
                return True
        return False

    async def initialize(self) -> None:
        """
        Initialize processor resources (AI clients, etc.).

        Override in subclasses for async initialization.
        """
        self._initialized = True

    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """
        Process media content and extract text/metadata.

        This method handles common logic and delegates to _process_content.

        Args:
            event: The curation event with source file info
            tenant_config: Optional tenant-specific configuration

        Returns:
            ProcessorResult with extracted content

        Raises:
            ProcessorNotFoundError: If MIME type not supported
            RetryableError: For temporary failures
            NonRetryableError: For permanent failures
        """
        start_time = datetime.utcnow()

        logger.info(
            f"Processing content with {self.name}",
            extra={
                "event_id": str(event.event_id),
                "trace_id": str(event.trace_id),
                "mime_type": event.mime_type,
                "raw_gcs_uri": event.raw_gcs_uri,
            },
        )

        if not self.supports(event.mime_type):
            from media_curation.domain.exceptions import ProcessorNotFoundError

            raise ProcessorNotFoundError(
                event.mime_type,
                event_id=event.event_id,
                trace_id=event.trace_id,
            )

        if not self._initialized:
            await self.initialize()

        try:
            result = await self._process_content(event, tenant_config)

            # Calculate processing duration
            end_time = datetime.utcnow()
            result.processing_duration_ms = int(
                (end_time - start_time).total_seconds() * 1000
            )

            logger.info(
                "Content processed successfully",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": str(event.trace_id),
                    "processor": self.name,
                    "duration_ms": result.processing_duration_ms,
                    "text_length": len(result.extracted_text),
                },
            )

            return result

        except CurationError:
            raise
        except Exception as e:
            logger.exception(
                f"Unexpected error in {self.name}",
                extra={
                    "event_id": str(event.event_id),
                    "trace_id": str(event.trace_id),
                },
            )
            raise NonRetryableError(
                f"Processor error: {e}",
                event_id=event.event_id,
                trace_id=event.trace_id,
            )

    @abstractmethod
    async def _process_content(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """
        Actual content processing logic.

        Must be implemented by subclasses.

        Args:
            event: The curation event
            tenant_config: Tenant configuration

        Returns:
            ProcessorResult with extracted content
        """
        pass

    async def cleanup(self) -> None:
        """
        Cleanup processor resources.

        Override in subclasses for cleanup logic.
        """
        pass
