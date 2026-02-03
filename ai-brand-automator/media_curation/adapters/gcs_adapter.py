"""
GCS Adapter - Google Cloud Storage implementation of StoragePort.

Handles file operations in GCS buckets for the curation pipeline.
"""

import asyncio
import logging
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Optional

from django.conf import settings

from media_curation.ports.storage_port import StoragePort, FileInfo
from media_curation.domain.exceptions import StorageError


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=4)


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    """
    Parse a GCS URI into bucket and object name.

    Args:
        gcs_uri: Full GCS URI (gs://bucket/path/to/file)

    Returns:
        Tuple of (bucket_name, object_name)

    Raises:
        ValueError: If URI is not a valid GCS URI
    """
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {gcs_uri}")

    path = gcs_uri[5:]  # Remove "gs://"
    parts = path.split("/", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid GCS URI (no object path): {gcs_uri}")

    return parts[0], parts[1]


class GCSAdapter(StoragePort):
    """
    Google Cloud Storage adapter implementing StoragePort.

    Uses the google-cloud-storage library for all GCS operations.
    Provides async wrappers around synchronous GCS client methods.
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        default_bucket: Optional[str] = None,
    ):
        """
        Initialize the GCS adapter.

        Args:
            project_id: GCP project ID (uses settings if not provided)
            credentials_path: Path to service account JSON file (optional if using ADC)
            default_bucket: Default bucket name for operations
        """
        # Set project_id and default_bucket first (used even in mock mode)
        self.project_id = project_id or getattr(settings, "GCP_PROJECT_ID", None)
        self.default_bucket = default_bucket or getattr(
            settings, "MEDIA_CURATION", {}
        ).get("STORAGE", {}).get("CURATED_BUCKET", "curated-content")

        # Lazy import to avoid issues when google-cloud-storage is not installed
        try:
            from google.cloud import storage

            self._storage_available = True
        except ImportError:
            self._storage_available = False
            logger.warning("google-cloud-storage not installed, using mock mode")
            self.client = None
            return

        try:
            if credentials_path:
                self.client = storage.Client.from_service_account_json(
                    credentials_path,
                    project=self.project_id,
                )
            else:
                # Use Application Default Credentials
                self.client = storage.Client(project=self.project_id)
        except Exception as e:
            # Handle credential errors gracefully - fall back to mock mode
            logger.warning(f"Failed to initialize GCS client: {e}. Using mock mode.")
            self._storage_available = False
            self.client = None
            return

        logger.info(
            "GCS adapter initialized",
            extra={
                "project_id": self.project_id,
                "default_bucket": self.default_bucket,
            },
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

    async def exists(self, path: str) -> bool:
        """Check if a file exists in GCS."""
        if not self._storage_available:
            return False

        def _check():
            try:
                bucket, blob_name = self._get_bucket_and_blob(path)
                blob = bucket.blob(blob_name)
                return blob.exists()
            except Exception as e:
                logger.error(f"Error checking file existence: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)

    async def get_file_info(self, path: str) -> FileInfo:
        """Get metadata about a file."""
        if not self._storage_available:
            raise StorageError(f"Storage not available for path: {path}")

        def _get_info():
            from google.cloud.exceptions import NotFound

            try:
                bucket, blob_name = self._get_bucket_and_blob(path)
                blob = bucket.blob(blob_name)
                blob.reload()  # Fetch metadata

                return FileInfo(
                    path=path,
                    bucket=bucket.name,
                    name=blob_name,
                    size_bytes=blob.size or 0,
                    content_type=blob.content_type or "application/octet-stream",
                    created_at=blob.time_created.isoformat()
                    if blob.time_created
                    else None,
                    updated_at=blob.updated.isoformat() if blob.updated else None,
                    md5_hash=blob.md5_hash,
                    metadata=blob.metadata or {},
                )
            except NotFound:
                raise StorageError(f"File not found: {path}")
            except Exception as e:
                raise StorageError(f"Error getting file info: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get_info)

    async def download_as_bytes(self, path: str) -> bytes:
        """Download file content as bytes."""
        if not self._storage_available:
            raise StorageError(f"Storage not available for path: {path}")

        def _download():
            from google.cloud.exceptions import NotFound

            try:
                bucket, blob_name = self._get_bucket_and_blob(path)
                blob = bucket.blob(blob_name)
                return blob.download_as_bytes()
            except NotFound:
                raise StorageError(f"File not found: {path}")
            except Exception as e:
                raise StorageError(f"Error downloading file: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _download)

    async def download_to_file(self, path: str, destination: str) -> str:
        """Download file to local filesystem."""
        if not self._storage_available:
            raise StorageError(f"Storage not available for path: {path}")

        def _download():
            from google.cloud.exceptions import NotFound

            try:
                bucket, blob_name = self._get_bucket_and_blob(path)
                blob = bucket.blob(blob_name)
                blob.download_to_filename(destination)
                return destination
            except NotFound:
                raise StorageError(f"File not found: {path}")
            except Exception as e:
                raise StorageError(f"Error downloading file: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _download)

    async def upload_from_bytes(
        self,
        content: bytes,
        destination_path: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> FileInfo:
        """Upload bytes to storage."""
        if not self._storage_available:
            raise StorageError("Storage not available for upload")

        def _upload():
            try:
                bucket, blob_name = self._get_bucket_and_blob(destination_path)
                blob = bucket.blob(blob_name)

                if metadata:
                    blob.metadata = metadata

                blob.upload_from_string(content, content_type=content_type)
                blob.reload()

                return FileInfo(
                    path=destination_path,
                    bucket=bucket.name,
                    name=blob_name,
                    size_bytes=blob.size or len(content),
                    content_type=content_type,
                    created_at=blob.time_created.isoformat()
                    if blob.time_created
                    else None,
                    updated_at=blob.updated.isoformat() if blob.updated else None,
                    md5_hash=blob.md5_hash,
                    metadata=blob.metadata or {},
                )
            except Exception as e:
                raise StorageError(f"Error uploading file: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _upload)

    async def upload_from_file(
        self,
        source: str,
        destination_path: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> FileInfo:
        """Upload local file to storage."""
        if not self._storage_available:
            raise StorageError("Storage not available for upload")

        def _upload():
            try:
                bucket, blob_name = self._get_bucket_and_blob(destination_path)
                blob = bucket.blob(blob_name)

                # Auto-detect content type if not provided
                if content_type is None:
                    detected_type, _ = mimetypes.guess_type(source)
                    final_content_type = detected_type or "application/octet-stream"
                else:
                    final_content_type = content_type

                if metadata:
                    blob.metadata = metadata

                blob.upload_from_filename(source, content_type=final_content_type)
                blob.reload()

                return FileInfo(
                    path=destination_path,
                    bucket=bucket.name,
                    name=blob_name,
                    size_bytes=blob.size or 0,
                    content_type=final_content_type,
                    created_at=blob.time_created.isoformat()
                    if blob.time_created
                    else None,
                    updated_at=blob.updated.isoformat() if blob.updated else None,
                    md5_hash=blob.md5_hash,
                    metadata=blob.metadata or {},
                )
            except Exception as e:
                raise StorageError(f"Error uploading file: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _upload)

    async def generate_signed_url(
        self,
        path: str,
        expiration_seconds: int = 3600,
    ) -> str:
        """Generate a signed URL for temporary access."""
        if not self._storage_available:
            raise StorageError("Storage not available for signed URL generation")

        def _generate():
            try:
                bucket, blob_name = self._get_bucket_and_blob(path)
                blob = bucket.blob(blob_name)
                return blob.generate_signed_url(
                    expiration=timedelta(seconds=expiration_seconds),
                    method="GET",
                )
            except Exception as e:
                raise StorageError(f"Error generating signed URL: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _generate)

    async def save_json(
        self,
        data: dict,
        destination_path: str,
        metadata: Optional[dict] = None,
    ) -> FileInfo:
        """
        Save a dictionary as JSON to GCS.

        Convenience method for saving curated documents.

        Args:
            data: Dictionary to serialize as JSON
            destination_path: Full GCS URI (gs://bucket/path)
            metadata: Optional metadata to attach to the blob

        Returns:
            FileInfo for the uploaded file
        """
        import json

        content = json.dumps(data, indent=2, default=str).encode("utf-8")
        return await self.upload_from_bytes(
            content=content,
            destination_path=destination_path,
            content_type="application/json",
            metadata=metadata,
        )

    async def is_healthy(self) -> bool:
        """Check if storage service is available."""
        if not self._storage_available:
            return False

        def _check():
            try:
                # Try to list buckets (lightweight health check)
                list(self.client.list_buckets(max_results=1))
                return True
            except Exception as e:
                logger.warning(f"GCS health check failed: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)
