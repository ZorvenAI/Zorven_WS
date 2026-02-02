"""
Storage Port.

Abstract interface for cloud storage operations.
Concrete implementation: GCSAdapter (Google Cloud Storage).

Note: This can reuse the GCS adapter from data_ingestion with minor extensions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class FileInfo:
    """Metadata about a stored file."""

    path: str  # Full GCS URI: gs://bucket/path/to/file
    bucket: str
    name: str  # Object name within bucket
    size_bytes: int
    content_type: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    md5_hash: Optional[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class StoragePort(ABC):
    """
    Abstract interface for cloud storage operations.

    Provides file reading, writing, and metadata operations.
    """

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """
        Check if a file exists.

        Args:
            path: GCS URI (gs://bucket/path/to/file)

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_file_info(self, path: str) -> FileInfo:
        """
        Get metadata about a file.

        Args:
            path: GCS URI (gs://bucket/path/to/file)

        Returns:
            FileInfo with metadata

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def download_as_bytes(self, path: str) -> bytes:
        """
        Download file content as bytes.

        Args:
            path: GCS URI (gs://bucket/path/to/file)

        Returns:
            File content as bytes

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def download_to_file(self, path: str, destination: str) -> str:
        """
        Download file to local filesystem.

        Args:
            path: GCS URI (gs://bucket/path/to/file)
            destination: Local file path

        Returns:
            Local file path

        Raises:
            StorageNotFoundError: If file doesn't exist
        """
        pass

    @abstractmethod
    async def upload_from_bytes(
        self,
        content: bytes,
        destination_path: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileInfo:
        """
        Upload bytes to storage.

        Args:
            content: File content as bytes
            destination_path: GCS URI for destination
            content_type: MIME type
            metadata: Optional custom metadata

        Returns:
            FileInfo for uploaded file
        """
        pass

    @abstractmethod
    async def upload_from_file(
        self,
        source: str,
        destination_path: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> FileInfo:
        """
        Upload local file to storage.

        Args:
            source: Local file path
            destination_path: GCS URI for destination
            content_type: MIME type (auto-detected if not provided)
            metadata: Optional custom metadata

        Returns:
            FileInfo for uploaded file
        """
        pass

    @abstractmethod
    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600,
    ) -> str:
        """
        Generate a signed URL for temporary access.

        Args:
            path: GCS URI
            expiration_seconds: URL validity duration

        Returns:
            Signed URL string
        """
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if storage service is available."""
        pass
