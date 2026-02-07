"""
GCS Adapter - Google Cloud Storage implementation of StoragePort.

Handles file operations in GCS buckets for the ingestion pipeline.
"""

import logging
from typing import Optional
from google.cloud import storage
from google.cloud.exceptions import NotFound, GoogleCloudError

from data_ingestion.ports.storage_port import StoragePort
from data_ingestion.domain.models import FileMetadata
from data_ingestion.domain.exceptions import (
    StorageOperationError,
    FileNotFoundInLandingError,
)
from data_ingestion.domain.path_generator import parse_gcs_uri


logger = logging.getLogger(__name__)


class GCSAdapter(StoragePort):
    """
    Google Cloud Storage adapter implementing StoragePort.

    Uses the google-cloud-storage library for all GCS operations.
    """

    def __init__(
        self,
        project_id: str,
        credentials_path: Optional[str] = None,
        default_bucket: Optional[str] = None,
    ):
        """
        Initialize the GCS adapter.

        Args:
            project_id: GCP project ID
            credentials_path: Path to service account JSON file (optional if using ADC)
            default_bucket: Default bucket name for operations
        """
        self.project_id = project_id
        self.default_bucket = default_bucket

        if credentials_path:
            self.client = storage.Client.from_service_account_json(
                credentials_path,
                project=project_id,
            )
        else:
            # Use Application Default Credentials
            self.client = storage.Client(project=project_id)

        logger.info(
            "GCS adapter initialized",
            extra={"project_id": project_id, "default_bucket": default_bucket},
        )

    def _get_bucket_and_blob(self, gcs_path: str) -> tuple:
        """
        Parse GCS path and return bucket and blob objects.

        Args:
            gcs_path: Full GCS URI (gs://bucket/path/to/file)

        Returns:
            Tuple of (bucket, blob_name)
        """
        bucket_name, blob_name = parse_gcs_uri(gcs_path)
        bucket = self.client.bucket(bucket_name)
        return bucket, blob_name

    def check_exists(self, file_path: str) -> bool:
        """
        Check if a file exists in GCS.

        Args:
            file_path: GCS URI (gs://bucket/path/to/file)

        Returns:
            True if file exists, False otherwise

        Raises:
            StorageOperationError: If there's a GCS error
        """
        try:
            bucket, blob_name = self._get_bucket_and_blob(file_path)
            blob = bucket.blob(blob_name)
            return blob.exists()
        except GoogleCloudError as e:
            logger.error(
                "GCS error checking file existence",
                extra={"file_path": file_path, "error": str(e)},
            )
            raise StorageOperationError(
                operation="check_exists",
                path=file_path,
                cause=e,
            )

    def move_file(self, source_path: str, destination_path: str) -> str:
        """
        Move a file within GCS (copy + delete source).

        Args:
            source_path: Source GCS URI
            destination_path: Destination GCS URI

        Returns:
            The destination path where file was moved

        Raises:
            FileNotFoundInLandingError: If source file doesn't exist
            StorageOperationError: If there's a GCS error
        """
        try:
            # Parse source
            source_bucket, source_blob_name = self._get_bucket_and_blob(source_path)
            source_blob = source_bucket.blob(source_blob_name)

            # Check source exists
            if not source_blob.exists():
                raise FileNotFoundInLandingError(file_path=source_path)

            # Parse destination
            dest_bucket, dest_blob_name = self._get_bucket_and_blob(destination_path)

            # Guard: if source and destination are the same, skip the move
            # to avoid copy-then-delete destroying the file.
            if (
                source_bucket.name == dest_bucket.name
                and source_blob_name == dest_blob_name
            ):
                logger.info(
                    "Source and destination are identical, skipping move",
                    extra={"path": source_path},
                )
                return destination_path

            # Copy to destination
            source_bucket.copy_blob(
                source_blob,
                dest_bucket,
                dest_blob_name,
            )

            # Delete source
            source_blob.delete()

            logger.debug(
                "File moved successfully",
                extra={"source": source_path, "destination": destination_path},
            )

            return destination_path

        except FileNotFoundInLandingError:
            raise
        except GoogleCloudError as e:
            logger.error(
                "GCS error moving file",
                extra={
                    "source": source_path,
                    "destination": destination_path,
                    "error": str(e),
                },
            )
            raise StorageOperationError(
                operation="move_file",
                path=source_path,
                cause=e,
            )

    def copy_file(self, source_path: str, destination_path: str) -> str:
        """
        Copy a file within GCS.

        Args:
            source_path: Source GCS URI
            destination_path: Destination GCS URI

        Returns:
            The destination path where file was copied

        Raises:
            FileNotFoundInLandingError: If source file doesn't exist
            StorageOperationError: If there's a GCS error
        """
        try:
            # Parse source
            source_bucket, source_blob_name = self._get_bucket_and_blob(source_path)
            source_blob = source_bucket.blob(source_blob_name)

            # Check source exists
            if not source_blob.exists():
                raise FileNotFoundInLandingError(file_path=source_path)

            # Parse destination
            dest_bucket, dest_blob_name = self._get_bucket_and_blob(destination_path)

            # Copy to destination
            source_bucket.copy_blob(
                source_blob,
                dest_bucket,
                dest_blob_name,
            )

            logger.debug(
                "File copied successfully",
                extra={"source": source_path, "destination": destination_path},
            )

            return destination_path

        except FileNotFoundInLandingError:
            raise
        except GoogleCloudError as e:
            logger.error(
                "GCS error copying file",
                extra={
                    "source": source_path,
                    "destination": destination_path,
                    "error": str(e),
                },
            )
            raise StorageOperationError(
                operation="copy_file",
                path=source_path,
                cause=e,
            )

    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file from GCS.

        Args:
            file_path: GCS URI to delete

        Returns:
            True if file was deleted, False if it didn't exist

        Raises:
            StorageOperationError: If there's a GCS error
        """
        try:
            bucket, blob_name = self._get_bucket_and_blob(file_path)
            blob = bucket.blob(blob_name)

            if not blob.exists():
                return False

            blob.delete()
            logger.debug("File deleted", extra={"file_path": file_path})
            return True

        except NotFound:
            return False
        except GoogleCloudError as e:
            logger.error(
                "GCS error deleting file",
                extra={"file_path": file_path, "error": str(e)},
            )
            raise StorageOperationError(
                operation="delete_file",
                path=file_path,
                cause=e,
            )

    def get_metadata(self, file_path: str) -> FileMetadata:
        """
        Get metadata for a file in GCS.

        Args:
            file_path: GCS URI

        Returns:
            FileMetadata dict with file information

        Raises:
            FileNotFoundInLandingError: If file doesn't exist
            StorageOperationError: If there's a GCS error
        """
        try:
            bucket, blob_name = self._get_bucket_and_blob(file_path)
            blob = bucket.blob(blob_name)

            # Reload to get metadata
            blob.reload()

            return FileMetadata(
                bucket=bucket.name,
                path=blob_name,
                full_uri=file_path,
                size_bytes=blob.size or 0,
                content_type=blob.content_type or "application/octet-stream",
                created_at=blob.time_created,
                updated_at=blob.updated,
                md5_hash=blob.md5_hash,
                etag=blob.etag,
            )

        except NotFound:
            raise FileNotFoundInLandingError(file_path=file_path)
        except GoogleCloudError as e:
            logger.error(
                "GCS error getting metadata",
                extra={"file_path": file_path, "error": str(e)},
            )
            raise StorageOperationError(
                operation="get_metadata",
                path=file_path,
                cause=e,
            )

    def list_files(self, prefix: str, bucket_name: Optional[str] = None) -> list[str]:
        """
        List files in GCS with a given prefix.

        Args:
            prefix: Path prefix to filter (e.g., "tenant-1/raw/2026/01/")
            bucket_name: Bucket to list from (uses default if not provided)

        Returns:
            List of GCS URIs matching the prefix

        Raises:
            StorageOperationError: If there's a GCS error
        """
        try:
            bucket_name = bucket_name or self.default_bucket
            if not bucket_name:
                raise ValueError("No bucket specified and no default bucket configured")

            bucket = self.client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=prefix)

            return [f"gs://{bucket_name}/{blob.name}" for blob in blobs]

        except GoogleCloudError as e:
            logger.error(
                "GCS error listing files",
                extra={"prefix": prefix, "bucket": bucket_name, "error": str(e)},
            )
            raise StorageOperationError(
                operation="list_files",
                path=f"gs://{bucket_name}/{prefix}",
                cause=e,
            )

    def upload_file(
        self,
        local_path: str,
        destination_path: str,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload a local file to GCS.

        Args:
            local_path: Local file path
            destination_path: Destination GCS URI
            content_type: Optional content type

        Returns:
            The GCS URI where file was uploaded

        Raises:
            StorageOperationError: If there's a GCS error
        """
        try:
            bucket, blob_name = self._get_bucket_and_blob(destination_path)
            blob = bucket.blob(blob_name)

            blob.upload_from_filename(local_path, content_type=content_type)

            logger.debug(
                "File uploaded",
                extra={"local_path": local_path, "destination": destination_path},
            )

            return destination_path

        except GoogleCloudError as e:
            logger.error(
                "GCS error uploading file",
                extra={
                    "local_path": local_path,
                    "destination": destination_path,
                    "error": str(e),
                },
            )
            raise StorageOperationError(
                operation="upload_file",
                path=destination_path,
                cause=e,
            )

    def download_file(self, source_path: str, local_path: str) -> str:
        """
        Download a file from GCS to local filesystem.

        Args:
            source_path: Source GCS URI
            local_path: Local destination path

        Returns:
            The local path where file was downloaded

        Raises:
            FileNotFoundInLandingError: If source file doesn't exist
            StorageOperationError: If there's a GCS error
        """
        try:
            bucket, blob_name = self._get_bucket_and_blob(source_path)
            blob = bucket.blob(blob_name)

            if not blob.exists():
                raise FileNotFoundInLandingError(file_path=source_path)

            blob.download_to_filename(local_path)

            logger.debug(
                "File downloaded",
                extra={"source": source_path, "local_path": local_path},
            )

            return local_path

        except FileNotFoundInLandingError:
            raise
        except GoogleCloudError as e:
            logger.error(
                "GCS error downloading file",
                extra={
                    "source": source_path,
                    "local_path": local_path,
                    "error": str(e),
                },
            )
            raise StorageOperationError(
                operation="download_file",
                path=source_path,
                cause=e,
            )
