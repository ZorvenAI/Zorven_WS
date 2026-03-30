"""Tests for GCSClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.gcs_client import GCSClient


class TestGCSClient:
    """Test GCS blueprint persistence client."""

    def test_gcs_disabled_mode(self):
        """No bucket_name means _ensure_client returns False."""
        client = GCSClient(project_id="", bucket_name="")
        assert client._ensure_client() is False

    @patch("app.services.gcs_client.json")
    def test_gcs_enabled_mode(self, mock_json):
        """With credentials_json, _ensure_client initializes GCS."""
        with (
            patch("google.cloud.storage.Client") as mock_storage,
            patch("google.oauth2.service_account.Credentials") as mock_creds,
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            mock_client_instance = MagicMock()
            mock_storage.return_value = mock_client_instance
            mock_json.loads.return_value = {"type": "service_account"}

            client = GCSClient(
                project_id="test-project",
                bucket_name="test-bucket",
                credentials_json='{"type": "service_account"}',
            )
            result = client._ensure_client()
            assert result is True

    async def test_upload_blueprint_success(self):
        """upload_blueprint returns GCS URI when client is configured."""
        client = GCSClient(bucket_name="test-bucket")
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        client._client = MagicMock()
        client._bucket = mock_bucket

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = None
            uri = await client.upload_blueprint(
                "test-tenant", "job-123", {"blueprint": {}}
            )

        assert uri.startswith("gs://test-bucket/caa/test-tenant/job-123/")
        assert "blueprint_" in uri

    async def test_download_blueprint_success(self):
        """download_blueprint returns parsed JSON."""
        client = GCSClient(bucket_name="test-bucket")
        mock_blob = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        client._client = MagicMock()
        client._bucket = mock_bucket

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = '{"blueprint": {"name": "Test"}}'
            result = await client.download_blueprint("test-tenant", "some/path.json")

        assert result == {"blueprint": {"name": "Test"}}

    async def test_upload_blueprint_failure_logs_warning(self):
        """upload_blueprint returns empty string on failure."""
        client = GCSClient(bucket_name="test-bucket")
        mock_bucket = MagicMock()
        mock_bucket.blob.side_effect = Exception("GCS error")
        client._client = MagicMock()
        client._bucket = mock_bucket

        uri = await client.upload_blueprint("test-tenant", "job-123", {"blueprint": {}})
        assert uri == ""
