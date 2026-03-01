"""
GCS client for uploading blog content and metadata.

In stub mode (no GCS config), returns a stub URI.
Uses asyncio.to_thread() for sync GCS operations.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class GCSClient:
    """Uploads blog Markdown and metadata to Google Cloud Storage."""

    def __init__(
        self,
        project_id: str = "",
        bucket_name: str = "",
        credentials_path: str = "",
        credentials_json: str = "",
    ) -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.credentials_path = credentials_path
        self.credentials_json = credentials_json
        self._client: Any = None
        self._stub_mode = not project_id or not bucket_name

        if self._stub_mode:
            logger.info("GCSClient running in stub mode (no GCS config)")
        else:
            logger.info("GCSClient configured for GCS project: %s", project_id)

    def _get_client(self) -> Any:
        """Lazy-initialize GCS client."""
        if self._client is None and not self._stub_mode:
            try:
                from google.cloud import storage

                if self.credentials_json:
                    import json as _json

                    from google.oauth2 import service_account

                    info = _json.loads(self.credentials_json)
                    creds = service_account.Credentials.from_service_account_info(info)
                    self._client = storage.Client(
                        credentials=creds, project=info.get("project_id")
                    )
                elif self.credentials_path:
                    self._client = storage.Client.from_service_account_json(
                        self.credentials_path
                    )
                else:
                    self._client = storage.Client(project=self.project_id)
            except Exception as exc:
                logger.warning("Failed to initialize GCS client: %s", exc)
                self._stub_mode = True
        return self._client

    async def upload_blog(
        self,
        tenant_id: str,
        slug: str,
        markdown_content: str,
        metadata: dict[str, Any],
    ) -> str:
        """
        Upload a blog post and its metadata to GCS.

        Path: gs://{bucket}/{tenant_id}/content/blogs/{YYYY}/{MM}/{slug}.md
        Also uploads: {slug}_meta.json alongside.

        Returns the full GCS URI string.
        """
        if self._stub_mode:
            uri = f"stub://no-gcs/{tenant_id}/content/blogs/{slug}.md"
            logger.debug("GCS stub mode: %s", uri)
            return uri

        try:
            now = datetime.now(timezone.utc)
            base_path = (
                f"{tenant_id}/content/blogs/{now.year}/{now.month:02d}/{slug}"
            )
            md_path = f"{base_path}.md"
            meta_path = f"{base_path}_meta.json"

            client = self._get_client()
            if client is None:
                return f"stub://no-gcs/{tenant_id}/content/blogs/{slug}.md"

            bucket = client.bucket(self.bucket_name)

            # Upload Markdown
            md_blob = bucket.blob(md_path)
            await asyncio.to_thread(
                md_blob.upload_from_string,
                markdown_content,
                content_type="text/markdown",
            )

            # Upload metadata JSON
            meta_blob = bucket.blob(meta_path)
            await asyncio.to_thread(
                meta_blob.upload_from_string,
                json.dumps(metadata, indent=2),
                content_type="application/json",
            )

            uri = f"gs://{self.bucket_name}/{md_path}"
            logger.info("Blog uploaded to %s", uri)
            return uri

        except Exception as exc:
            logger.warning(
                "Error uploading blog for tenant %s: %s", tenant_id, exc
            )
            return f"stub://upload-failed/{tenant_id}/content/blogs/{slug}.md"

    async def close(self) -> None:
        """Clean up GCS client."""
        self._client = None
