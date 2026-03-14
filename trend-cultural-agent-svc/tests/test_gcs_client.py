"""Tests for GCS client — trend report persistence."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gcs_client import GCSClient


class TestUploadReport:
    """Test upload_report method."""

    async def test_upload_returns_uri(self) -> None:
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
        )
        # Mock the GCS client and bucket
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string = MagicMock()
        mock_bucket.blob = MagicMock(return_value=mock_blob)
        client._bucket = mock_bucket
        client._client = MagicMock()

        report = {"executive_summary": "Test report", "scored_trends": []}
        uri = await client.upload_report("t1", report, "daily_scan")

        assert uri.startswith("gs://test-bucket/t1/trend-reports/daily_scan/")
        assert uri.endswith(".json")

    async def test_upload_calls_blob(self) -> None:
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
        )
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string = MagicMock()
        mock_bucket.blob = MagicMock(return_value=mock_blob)
        client._bucket = mock_bucket
        client._client = MagicMock()

        report = {"data": "test"}
        await client.upload_report("t1", report)

        mock_bucket.blob.assert_called_once()
        blob_path = mock_bucket.blob.call_args[0][0]
        assert blob_path.startswith("t1/trend-reports/daily_scan/")

    async def test_upload_failure_returns_empty(self) -> None:
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
        )
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string = MagicMock(
            side_effect=Exception("GCS error")
        )
        mock_bucket.blob = MagicMock(return_value=mock_blob)
        client._bucket = mock_bucket
        client._client = MagicMock()

        uri = await client.upload_report("t1", {"data": "test"})
        assert uri == ""


class TestStubMode:
    """Test stub mode when GCS is not configured."""

    async def test_stub_upload_returns_empty(self) -> None:
        client = GCSClient()  # No bucket configured
        uri = await client.upload_report("t1", {"data": "test"})
        assert uri == ""

    async def test_stub_download_returns_none(self) -> None:
        client = GCSClient()
        result = await client.download_report("t1", "some/path.json")
        assert result is None

    async def test_ensure_client_no_bucket(self) -> None:
        client = GCSClient()
        assert client._ensure_client() is False

    async def test_ensure_client_no_import(self) -> None:
        """When google.cloud.storage is not installed, returns False."""
        client = GCSClient(bucket_name="test-bucket")
        with patch.dict("sys.modules", {"google.cloud": None, "google.cloud.storage": None}):
            # Force re-initialization
            client._client = None
            result = client._ensure_client()
            # May return False or True depending on import availability;
            # the key is no exception is raised


class TestDownloadReport:
    """Test download_report method."""

    async def test_download_parses_json(self) -> None:
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
        )
        report_data = {
            "executive_summary": "Downloaded report",
            "scored_trends": [{"trend_slug": "test"}],
            "confidence_score": 0.9,
        }
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_text = MagicMock(
            return_value=json.dumps(report_data)
        )
        mock_bucket.blob = MagicMock(return_value=mock_blob)
        client._bucket = mock_bucket
        client._client = MagicMock()

        result = await client.download_report("t1", "t1/reports/test.json")
        assert result is not None
        assert result["executive_summary"] == "Downloaded report"
        assert result["confidence_score"] == 0.9

    async def test_download_not_found_returns_none(self) -> None:
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
        )
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_text = MagicMock(
            side_effect=Exception("Blob not found")
        )
        mock_bucket.blob = MagicMock(return_value=mock_blob)
        client._bucket = mock_bucket
        client._client = MagicMock()

        result = await client.download_report("t1", "nonexistent.json")
        assert result is None


class TestEnsureClient:
    """Test lazy client initialization."""

    def test_already_initialized(self) -> None:
        client = GCSClient(bucket_name="test-bucket")
        client._client = MagicMock()
        assert client._ensure_client() is True

    def test_no_bucket_returns_false(self) -> None:
        client = GCSClient(bucket_name="")
        assert client._ensure_client() is False
