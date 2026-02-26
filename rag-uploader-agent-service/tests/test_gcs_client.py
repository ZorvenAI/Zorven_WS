"""Tests for GCSClient."""

from __future__ import annotations

from app.services.gcs_client import GCSClient


class TestGCSClientStubMode:
    """Tests when GCS is not configured."""

    def test_stub_mode_when_no_project(self):
        client = GCSClient(project_id="", bucket_name="bucket")
        assert client.is_available is False

    def test_stub_mode_when_no_bucket(self):
        client = GCSClient(project_id="project", bucket_name="")
        assert client.is_available is False

    def test_available_when_both_configured(self):
        client = GCSClient(project_id="project", bucket_name="bucket")
        assert client.is_available is True

    async def test_upload_content_returns_empty_in_stub_mode(self):
        client = GCSClient(project_id="", bucket_name="")
        result = await client.upload_content("tenant", "file.md", "content")
        assert result == ""

    async def test_close_is_safe(self):
        client = GCSClient()
        await client.close()
        assert client._client is None
