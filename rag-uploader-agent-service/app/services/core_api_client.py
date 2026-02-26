"""
Core API client for registering BrandAssets in the Django backend.

Calls the internal asset registration endpoint so that files archived
by the rag-uploader appear in the file uploader UI. The returned
asset_id is included in the IngestionEvent metadata, allowing the
curation and RAG index consumers to update the BrandAsset status.
"""

import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class CoreApiClient:
    """Registers BrandAssets via the Django backend's internal API."""

    def __init__(self, base_url: str, service_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Lazy-initialize httpx client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    async def register_asset(
        self,
        tenant_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        gcs_uri: str,
    ) -> Optional[dict[str, Any]]:
        """Register a file as a BrandAsset in the Django backend.

        POST {base_url}/api/v1/internal/assets/register/
        Headers: X-Tenant-ID, X-Service-Token

        Returns:
            {"asset_id": int, "company_id": int, ...} on success,
            None on failure.
        """
        try:
            client = self._get_client()
            headers = {
                "X-Tenant-ID": tenant_id,
                "X-Service-Token": self.service_token,
            }
            payload = {
                "file_name": file_name,
                "file_type": file_type,
                "file_size": file_size,
                "gcs_uri": gcs_uri,
            }

            url = f"{self.base_url}/api/v1/internal/assets/register/"
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()

            data = resp.json()
            logger.info(
                "Registered asset: tenant=%s file='%s' asset_id=%s company_id=%s",
                tenant_id,
                file_name,
                data.get("asset_id"),
                data.get("company_id"),
            )
            return data

        except Exception as exc:
            logger.warning(
                "Failed to register asset for tenant %s file '%s': %s",
                tenant_id,
                file_name,
                exc,
            )
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
