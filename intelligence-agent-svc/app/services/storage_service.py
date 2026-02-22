"""
Tenant-scoped storage service for fetching financial documents from GCS.

In stub mode (no GCS config), returns None to signal missing data.
The ProxyEngine uses this to decide the calculation strategy.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StorageService:
    """Fetch tenant-scoped financial documents from GCS."""

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
            logger.info("StorageService running in stub mode (no GCS config)")
        else:
            logger.info("StorageService configured for GCS project: %s", project_id)

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

    async def fetch_financial_data(
        self, tenant_id: str, file_id: str = ""
    ) -> Optional[dict[str, Any]]:
        """
        Fetch processed financial data from GCS.

        Path: gs://{bucket}/{tenant_id}/processed/{file_id or 'financials.json'}

        Returns:
            Parsed JSON dict or None if not found / stub mode.
        """
        if self._stub_mode:
            logger.debug(
                "StorageService stub: no financial data for tenant %s", tenant_id
            )
            return None

        try:
            client = self._get_client()
            if client is None:
                return None

            bucket = client.bucket(self.bucket_name)
            filename = file_id or "financials.json"
            blob_path = f"{tenant_id}/processed/{filename}"
            blob = bucket.blob(blob_path)

            if not blob.exists():
                logger.info("Financial data not found: gs://%s/%s", self.bucket_name, blob_path)
                return None

            content = blob.download_as_text()
            data = json.loads(content)
            logger.info("Fetched financial data for tenant %s", tenant_id)
            return data

        except Exception as exc:
            logger.warning(
                "Error fetching financial data for tenant %s: %s", tenant_id, exc
            )
            return None
