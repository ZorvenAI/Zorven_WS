"""Tests for CoreApiClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.core_api_client import CoreApiClient


class TestCoreApiClient:
    """Tests for the Django backend API client."""

    async def test_register_asset_success(self):
        """Successful asset registration returns data dict."""
        client = CoreApiClient(base_url="http://backend:8001", service_token="token")

        # httpx.Response methods (json, raise_for_status) are sync
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "asset_id": 42,
            "company_id": 7,
            "file_name": "report.pdf",
            "pipeline_status": "pending",
        }

        mock_http = AsyncMock()
        mock_http.post.return_value = mock_response
        client._client = mock_http

        result = await client.register_asset(
            tenant_id="1",
            file_name="report.pdf",
            file_type="application/pdf",
            file_size=1024,
            gcs_uri="gs://bucket/path/report.pdf",
        )

        assert result is not None
        assert result["asset_id"] == 42
        assert result["company_id"] == 7

        # Verify correct URL and headers
        call_args = mock_http.post.call_args
        assert "/api/v1/internal/assets/register/" in call_args[0][0]
        assert call_args[1]["headers"]["X-Tenant-ID"] == "1"
        assert call_args[1]["headers"]["X-Service-Token"] == "token"

    async def test_register_asset_failure_returns_none(self):
        """Failed registration returns None (non-fatal)."""
        client = CoreApiClient(base_url="http://backend:8001", service_token="token")

        mock_http = AsyncMock()
        mock_http.post.side_effect = Exception("Connection refused")
        client._client = mock_http

        result = await client.register_asset(
            tenant_id="1",
            file_name="report.pdf",
            file_type="application/pdf",
            file_size=1024,
            gcs_uri="gs://bucket/path/report.pdf",
        )

        assert result is None

    async def test_close(self):
        """close() properly shuts down the HTTP client."""
        client = CoreApiClient(base_url="http://backend:8001", service_token="token")
        mock_http = AsyncMock()
        client._client = mock_http
        await client.close()
        mock_http.aclose.assert_called_once()
        assert client._client is None

    async def test_close_when_no_client(self):
        """close() is safe when no client was created."""
        client = CoreApiClient(base_url="http://backend:8001", service_token="token")
        await client.close()  # Should not raise
