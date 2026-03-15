"""GCS client for VoC report persistence."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GCSClient:
    """Google Cloud Storage client for report persistence."""

    def __init__(
        self,
        project_id: str,
        bucket_name: str,
        credentials_json: str = "",
    ) -> None:
        self._project_id = project_id
        self._bucket_name = bucket_name
        self._credentials_json = credentials_json
        self._client = None
        self._bucket = None

    def _ensure_client(self) -> None:
        """Lazy-initialize GCS client."""
        if self._client:
            return
        try:
            from google.cloud import storage

            if self._credentials_json:
                import tempfile
                import os

                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                ) as f:
                    f.write(self._credentials_json)
                    cred_path = f.name
                self._client = storage.Client.from_service_account_json(
                    cred_path
                )
                os.unlink(cred_path)
            else:
                self._client = storage.Client(project=self._project_id)

            self._bucket = self._client.bucket(self._bucket_name)
            logger.info(
                "GCS client initialized: bucket=%s", self._bucket_name
            )
        except Exception as exc:
            logger.warning("GCS client init failed: %s", exc)

    async def upload_report(
        self,
        tenant_id: str,
        report_id: str,
        report_data: dict[str, Any],
        content_type: str = "application/json",
    ) -> str:
        """Upload a VoC report to GCS. Returns the GCS URI."""
        self._ensure_client()
        if not self._bucket:
            logger.warning("GCS bucket not available, skipping upload")
            return ""

        try:
            path = f"voc-reports/{tenant_id}/{report_id}.json"
            blob = self._bucket.blob(path)
            blob.upload_from_string(
                json.dumps(report_data, indent=2),
                content_type=content_type,
            )
            uri = f"gs://{self._bucket_name}/{path}"
            logger.info("Report uploaded: %s", uri)
            return uri
        except Exception as exc:
            logger.warning("GCS upload failed: %s", exc)
            return ""
