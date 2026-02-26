"""
GCS client for uploading content to the landing zone.

When upstream nodes (e.g., blog_author) produce content but only have
stub GCS URIs (no real GCS config), the rag-uploader uploads the
content to GCS itself before emitting an IngestionEvent.

In stub mode (no GCS config), returns empty string and logs a warning.
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GCSClient:
    """Uploads content to GCS landing zone for the ingestion pipeline."""

    def __init__(
        self,
        project_id: str = "",
        bucket_name: str = "",
        credentials_path: str = "",
    ) -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.credentials_path = credentials_path
        self._client: Any = None
        self._stub_mode = not project_id or not bucket_name

        if self._stub_mode:
            logger.info("GCSClient running in stub mode (no GCS config)")
        else:
            logger.info(
                "GCSClient configured for project: %s bucket: %s",
                project_id,
                bucket_name,
            )

    def _get_client(self) -> Any:
        """Lazy-initialize GCS client."""
        if self._client is None and not self._stub_mode:
            try:
                from google.cloud import storage

                if self.credentials_path:
                    self._client = storage.Client.from_service_account_json(
                        self.credentials_path
                    )
                else:
                    self._client = storage.Client(project=self.project_id)
            except Exception as exc:
                logger.warning("Failed to initialize GCS client: %s", exc)
                self._stub_mode = True
        return self._client

    @property
    def is_available(self) -> bool:
        """True when GCS credentials are configured."""
        return not self._stub_mode

    async def upload_content(
        self,
        tenant_id: str,
        filename: str,
        content: str,
        content_type: str = "text/markdown",
    ) -> str:
        """Upload text content to GCS landing zone.

        Path: gs://{bucket}/_landing/{tenant_id}/{filename}

        Returns the full GCS URI, or empty string on failure.
        """
        if self._stub_mode:
            logger.warning("GCS not configured — cannot upload content to landing zone")
            return ""

        try:
            # Sanitize filename to prevent path traversal
            safe_filename = (
                filename.replace("/", "_").replace("..", "_").replace("\\", "_")
            )
            object_path = f"_landing/{tenant_id}/{safe_filename}"

            client = self._get_client()
            if client is None:
                return ""

            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(object_path)
            await asyncio.to_thread(
                blob.upload_from_string, content, content_type=content_type
            )

            uri = f"gs://{self.bucket_name}/{object_path}"
            logger.info("Content uploaded to %s", uri)
            return uri

        except Exception as exc:
            logger.warning("Error uploading content for tenant %s: %s", tenant_id, exc)
            return ""

    async def close(self) -> None:
        """Clean up GCS client."""
        self._client = None
