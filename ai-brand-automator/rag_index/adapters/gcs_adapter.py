"""
GCS Adapter.

Concrete implementation of GCSPort for reading curated documents
from Google Cloud Storage.
"""

import json
import logging
from typing import Any, Optional

from django.conf import settings

from rag_index.domain.exceptions import (
    GCSNotFoundError,
    GCSReadError,
    InvalidGCSURIError,
)
from rag_index.ports.gcs_port import GCSPort

logger = logging.getLogger(__name__)


class GCSAdapter(GCSPort):
    """Concrete adapter for GCS operations.

    This adapter handles reading curated documents from GCS,
    which are then synced to Vertex AI Search.

    Configuration is loaded from Django settings:
    - GCS_PROJECT_ID: GCP project ID
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        mock_mode: bool = False,
    ):
        """Initialize GCS adapter.

        Args:
            project_id: GCP project ID (defaults to settings)
            mock_mode: If True, use mock mode without real GCS calls
        """
        self.project_id = project_id or getattr(settings, "GCS_PROJECT_ID", None)
        self.mock_mode = mock_mode or getattr(settings, "GCS_MOCK_MODE", False)
        self._client = None
        self._initialized = False

    def _get_client(self):
        """Get or create the GCS client.

        Lazy initialization to avoid import errors when SDK is not installed.
        """
        if self.mock_mode:
            return None

        if self._client is None:
            try:
                from google.cloud import storage

                self._client = storage.Client(project=self.project_id)
                self._initialized = True
            except ImportError:
                logger.warning(
                    "google-cloud-storage not installed. "
                    "Using mock mode for development."
                )
                self._client = None
                self._initialized = False
            except Exception as e:
                logger.error(f"Failed to initialize GCS client: {e}")
                self._client = None
                self._initialized = False
        return self._client

    async def read_document(self, gcs_uri: str) -> dict[str, Any]:
        """Read a curated document from GCS.

        Args:
            gcs_uri: The GCS URI (gs://bucket/path/file.json)

        Returns:
            The parsed document content as a dictionary
        """
        try:
            bucket_name, blob_path = self.parse_gcs_uri(gcs_uri)
            client = self._get_client()

            if client is None:
                # Mock mode for development/testing
                logger.info(f"[MOCK] Reading document from {gcs_uri}")
                return {
                    "id": blob_path.split("/")[-1].replace(".json", ""),
                    "content": "Mock document content",
                    "gcs_uri": gcs_uri,
                    "mock": True,
                }

            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            if not blob.exists():
                raise GCSNotFoundError(
                    message=f"Document not found: {gcs_uri}",
                    gcs_uri=gcs_uri,
                )

            content = blob.download_as_text()

            try:
                document = json.loads(content)
            except json.JSONDecodeError as e:
                raise GCSReadError(
                    message=f"Failed to parse JSON from {gcs_uri}: {e}",
                    gcs_uri=gcs_uri,
                )

            logger.debug(f"Read document from {gcs_uri}")
            return document

        except (GCSNotFoundError, GCSReadError, InvalidGCSURIError):
            raise
        except Exception as e:
            error_message = str(e)
            logger.error(f"Failed to read document from {gcs_uri}: {error_message}")

            if "NotFound" in error_message or "404" in error_message:
                raise GCSNotFoundError(
                    message=f"Document not found: {gcs_uri}",
                    gcs_uri=gcs_uri,
                )

            raise GCSReadError(
                message=f"Failed to read document: {error_message}",
                gcs_uri=gcs_uri,
            )

    async def file_exists(self, gcs_uri: str) -> bool:
        """Check if a file exists in GCS.

        Args:
            gcs_uri: The GCS URI to check

        Returns:
            True if file exists, False otherwise
        """
        try:
            bucket_name, blob_path = self.parse_gcs_uri(gcs_uri)
            client = self._get_client()

            if client is None:
                # Mock mode - assume files exist
                logger.info(f"[MOCK] Checking existence of {gcs_uri}")
                return True

            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)

            return blob.exists()

        except InvalidGCSURIError:
            raise
        except Exception as e:
            logger.error(f"Failed to check file existence: {e}")
            return False

    def parse_gcs_uri(self, gcs_uri: str) -> tuple[str, str]:
        """Parse a GCS URI into bucket and blob path.

        Args:
            gcs_uri: The GCS URI (gs://bucket/path/file.json)

        Returns:
            Tuple of (bucket_name, blob_path)
        """
        if not gcs_uri:
            raise InvalidGCSURIError(
                message="GCS URI cannot be empty",
                gcs_uri=gcs_uri,
            )

        if not gcs_uri.startswith("gs://"):
            raise InvalidGCSURIError(
                message=f"Invalid GCS URI format (must start with gs://): {gcs_uri}",
                gcs_uri=gcs_uri,
            )

        # Remove the gs:// prefix
        path = gcs_uri[5:]

        # Split into bucket and path
        parts = path.split("/", 1)

        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise InvalidGCSURIError(
                message=f"Invalid GCS URI format (missing bucket or path): {gcs_uri}",
                gcs_uri=gcs_uri,
            )

        bucket_name = parts[0]
        blob_path = parts[1]

        return bucket_name, blob_path

    async def check_connection(self) -> bool:
        """Check if the GCS connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            client = self._get_client()

            if client is None:
                return True  # Mock mode

            # Try to list buckets as a health check
            list(client.list_buckets(max_results=1))
            return True

        except Exception as e:
            logger.error(f"GCS connection check failed: {e}")
            return False

    async def close(self) -> None:
        """Close the GCS client connection."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.error(f"Error closing GCS client: {e}")
            finally:
                self._client = None
                self._initialized = False
