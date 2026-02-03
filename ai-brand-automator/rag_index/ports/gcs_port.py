"""
GCS Port.

Abstract interface for Google Cloud Storage operations.
"""

from abc import ABC, abstractmethod
from typing import Any


class GCSPort(ABC):
    """Abstract interface for GCS operations.

    This port defines the contract for reading curated documents
    from Google Cloud Storage.
    """

    @abstractmethod
    async def read_document(
        self,
        gcs_uri: str,
    ) -> dict[str, Any]:
        """Read a curated document from GCS.

        Args:
            gcs_uri: The GCS URI (gs://bucket/path/file.json)

        Returns:
            The parsed document content as a dictionary

        Raises:
            GCSNotFoundError: If the file doesn't exist
            GCSReadError: If reading fails
            InvalidGCSURIError: If the URI format is invalid
        """

    @abstractmethod
    async def file_exists(
        self,
        gcs_uri: str,
    ) -> bool:
        """Check if a file exists in GCS.

        Args:
            gcs_uri: The GCS URI to check

        Returns:
            True if file exists, False otherwise
        """

    @abstractmethod
    def parse_gcs_uri(
        self,
        gcs_uri: str,
    ) -> tuple[str, str]:
        """Parse a GCS URI into bucket and blob path.

        Args:
            gcs_uri: The GCS URI (gs://bucket/path/file.json)

        Returns:
            Tuple of (bucket_name, blob_path)

        Raises:
            InvalidGCSURIError: If the URI format is invalid
        """

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the GCS connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the GCS client connection."""
