"""
AI Content Processor Port.

Abstract interface for AI-powered content processing.
Concrete implementations: VertexAdapter (video/audio), VisionAdapter (image/PDF).
"""

from abc import ABC, abstractmethod
from typing import Optional

from media_curation.domain.models import (
    CurationEvent,
    ProcessorResult,
    TenantConfig,
)


class ContentProcessorPort(ABC):
    """
    Abstract interface for content processors (Strategy pattern).

    Each implementation handles a specific content type:
    - VideoProcessor: video/* MIME types
    - AudioProcessor: audio/* MIME types
    - ImageProcessor: image/* MIME types
    - DocumentProcessor: application/pdf, text/* MIME types
    """

    @property
    @abstractmethod
    def supported_mime_types(self) -> list[str]:
        """
        Return list of MIME types this processor supports.

        Examples: ["video/mp4", "video/webm", "video/*"]
        Wildcard patterns (video/*) are supported.
        """
        pass

    @abstractmethod
    async def process(
        self,
        event: CurationEvent,
        tenant_config: Optional[TenantConfig] = None,
    ) -> ProcessorResult:
        """
        Process media content and extract text/metadata.

        Args:
            event: The curation event with source file info
            tenant_config: Optional tenant-specific configuration

        Returns:
            ProcessorResult with extracted content

        Raises:
            RetryableError: For temporary failures
            NonRetryableError: For permanent failures
        """
        pass

    def supports(self, mime_type: str) -> bool:
        """
        Check if this processor supports the given MIME type.

        Args:
            mime_type: The MIME type to check (e.g., "video/mp4")

        Returns:
            True if supported, False otherwise
        """
        for supported in self.supported_mime_types:
            if supported.endswith("/*"):
                # Wildcard match: "video/*" matches "video/mp4"
                prefix = supported[:-1]  # "video/"
                if mime_type.startswith(prefix):
                    return True
            elif supported == mime_type:
                return True
        return False
