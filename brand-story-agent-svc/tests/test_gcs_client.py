"""Tests for GCSClient."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gcs_client import GCSClient


class TestGCSClient:
    """Test GCSClient."""

    def test_disabled_when_no_bucket(self):
        """Client should not init when no bucket configured."""
        client = GCSClient(project_id="", bucket_name="", credentials_path="")
        assert client._ensure_client() is False

    def test_upload_noop_when_disabled(self):
        """_ensure_client returns False when no bucket configured."""
        client = GCSClient(project_id="", bucket_name="", credentials_path="")
        assert client._ensure_client() is False

    async def test_upload_returns_empty_when_disabled(self):
        """upload_narrative should return empty string when disabled."""
        client = GCSClient(project_id="", bucket_name="", credentials_path="")

        result = await client.upload_narrative(
            tenant_id="test-tenant",
            job_id="job-123",
            narrative_data={"origin_story": {}},
        )

        assert result == ""

    async def test_upload_narrative_returns_path(self):
        """upload_narrative should return GCS path when bucket is set."""
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
            credentials_path="",
        )

        # Manually set client and bucket to bypass _ensure_client auth
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_bucket.blob.return_value = mock_blob
        client._client = MagicMock()
        client._bucket = mock_bucket

        result = await client.upload_narrative(
            tenant_id="test-tenant",
            job_id="job-123",
            narrative_data={"origin_story": {"content": "Story"}},
        )

        assert "gs://" in result
        assert "test-tenant" in result
        assert "brand-story" in result

    async def test_download_narrative_returns_data(self):
        """download_narrative should return parsed JSON."""
        client = GCSClient(
            project_id="test-project",
            bucket_name="test-bucket",
            credentials_path="",
        )

        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.download_as_text.return_value = json.dumps(
            {"origin_story": {"content": "Story"}}
        )
        mock_bucket.blob.return_value = mock_blob
        client._client = MagicMock()
        client._bucket = mock_bucket

        result = await client.download_narrative(
            tenant_id="test-tenant",
            narrative_path="brand-story/job-123/narrative_2024.json",
        )

        assert result is not None
        assert "origin_story" in result

    async def test_download_returns_none_when_disabled(self):
        """download_narrative should return None when not configured."""
        client = GCSClient(project_id="", bucket_name="", credentials_path="")

        result = await client.download_narrative(
            tenant_id="test-tenant",
            narrative_path="some/path.json",
        )

        assert result is None
