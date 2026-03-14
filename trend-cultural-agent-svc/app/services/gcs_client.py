"""GCS client for trend report persistence."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class GCSClient:
    """Async GCS client for trend report persistence.

    Supports 3 auth modes: JSON string, file path, ADC (Application Default
    Credentials). Returns empty strings in stub mode (no config).
    """

    def __init__(
        self,
        project_id: str = "",
        bucket_name: str = "",
        credentials_json: str = "",
        credentials_path: str = "",
    ) -> None:
        self._project_id = project_id
        self._bucket_name = bucket_name
        self._credentials_json = credentials_json
        self._credentials_path = credentials_path
        self._client: Any = None
        self._bucket: Any = None

    def _ensure_client(self) -> bool:
        """Lazy-init the GCS client."""
        if self._client is not None:
            return True
        if not self._bucket_name:
            return False
        try:
            from google.cloud import storage

            if self._credentials_json:
                from google.oauth2 import service_account

                info = json.loads(self._credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    info
                )
                self._client = storage.Client(
                    project=self._project_id, credentials=credentials
                )
            elif self._credentials_path:
                self._client = storage.Client.from_service_account_json(
                    self._credentials_path
                )
            else:
                self._client = storage.Client(project=self._project_id)
            self._bucket = self._client.bucket(self._bucket_name)
            return True
        except Exception as exc:
            logger.warning("GCS client init failed: %s", exc)
            return False

    async def upload_report(
        self,
        tenant_id: str,
        report_json: dict[str, Any],
        report_type: str = "daily_scan",
    ) -> str:
        """Upload trend report JSON to GCS. Returns GCS URI."""
        if not self._ensure_client():
            logger.info("GCS not configured, skipping upload")
            return ""
        try:
            date_slug = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
            path = f"{tenant_id}/trend-reports/{report_type}/{date_slug}.json"
            blob = self._bucket.blob(path)
            await asyncio.to_thread(
                blob.upload_from_string,
                json.dumps(report_json),
                content_type="application/json",
            )
            uri = f"gs://{self._bucket_name}/{path}"
            logger.info("Uploaded trend report to %s", uri)
            return uri
        except Exception as exc:
            logger.warning("GCS upload failed: %s", exc)
            return ""

    async def download_report(
        self, tenant_id: str, report_path: str
    ) -> dict[str, Any] | None:
        """Download a trend report from GCS."""
        if not self._ensure_client():
            return None
        try:
            blob = self._bucket.blob(report_path)
            data = await asyncio.to_thread(blob.download_as_text)
            return json.loads(data)
        except Exception as exc:
            logger.warning("GCS download failed: %s", exc)
            return None
