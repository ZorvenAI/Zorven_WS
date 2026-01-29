"""
Storage Port - Abstract interface for file storage operations.

This port defines how the domain layer interacts with file storage (GCS).
The actual implementation is provided by adapters (e.g., GCSAdapter).
"""

from abc import ABC, abstractmethod
from typing import Optional

from data_ingestion.domain.models import FileMetadata


class StoragePort(ABC):
    """
    Abstract interface for file storage operations.

    Implementations:
        - GCSAdapter: Google Cloud Storage implementation
        - MockStorageAdapter: For testing
    """

    @abstractmethod
    def check_exists(self, path: str) -> bool:
        """
        Check if a file exists at the given path.

        This should be a lightweight operation (HEAD request equivalent).

        Args:
            path: Full storage path (e.g., 'gs://bucket/path/to/file.mp4')
                  or object path within configured bucket

        Returns:
            True if file exists, False otherwise

        Raises:
            StorageOperationError: If the check fails due to network/permission issues
        """
        pass

    @abstractmethod
    def get_metadata(self, path: str) -> Optional[FileMetadata]:
        """
        Get metadata for a file at the given path.

        Args:
            path: Full storage path or object path within configured bucket

        Returns:
            FileMetadata if file exists, None if file doesn't exist

        Raises:
            StorageOperationError: If the operation fails
        """
        pass

    @abstractmethod
    def move_file(self, source_path: str, destination_path: str) -> str:
        """
        Move a file from source to destination.

        Note: In GCS, this is implemented as copy + delete since
        GCS doesn't support atomic rename across paths.

        Args:
            source_path: Full path to source file (e.g., 'gs://bucket/_landing/file.mp4')
            destination_path: Full path to destination (e.g., 'gs://bucket/tenant/raw/...')

        Returns:
            The full URI of the destination file

        Raises:
            FileNotFoundInLandingError: If source file doesn't exist
            StorageOperationError: If the move operation fails
        """
        pass

    @abstractmethod
    def copy_file(self, source_path: str, destination_path: str) -> str:
        """
        Copy a file from source to destination.

        Args:
            source_path: Full path to source file
            destination_path: Full path to destination

        Returns:
            The full URI of the destination file

        Raises:
            FileNotFoundInLandingError: If source file doesn't exist
            StorageOperationError: If the copy operation fails
        """
        pass

    @abstractmethod
    def delete_file(self, path: str) -> bool:
        """
        Delete a file at the given path.

        Args:
            path: Full path to the file to delete

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageOperationError: If the delete operation fails
        """
        pass

    @abstractmethod
    def list_files(self, prefix: str, max_results: int = 100) -> list[str]:
        """
        List files with the given prefix.

        Args:
            prefix: Path prefix to filter files (e.g., '_landing/')
            max_results: Maximum number of results to return

        Returns:
            List of file paths matching the prefix

        Raises:
            StorageOperationError: If the list operation fails
        """
        pass
