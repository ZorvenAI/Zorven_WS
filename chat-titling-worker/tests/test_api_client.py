"""Tests for CoreApiClient."""

import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.api_client import CoreApiClient


class TestCoreApiClient:
    """Tests for the CoreApiClient class."""

    async def test_update_title_success(self, httpx_mock):
        """200 response returns True."""
        httpx_mock.add_response(
            url="http://backend:8001/api/v1/ai/internal/title-session/abc-123/",
            method="PATCH",
            status_code=200,
            json={"status": "updated"},
        )

        client = CoreApiClient(
            base_url="http://backend:8001",
            worker_token="test-token",
        )

        result = await client.update_title("abc-123", "Test Title", "tenant-1")
        assert result is True

        await client.close()

    async def test_update_title_failure(self, httpx_mock):
        """Non-200 returns False."""
        httpx_mock.add_response(
            url="http://backend:8001/api/v1/ai/internal/title-session/abc-123/",
            method="PATCH",
            status_code=500,
            json={"error": "Internal server error"},
        )

        client = CoreApiClient(
            base_url="http://backend:8001",
            worker_token="test-token",
        )

        result = await client.update_title("abc-123", "Test Title", "tenant-1")
        assert result is False

        await client.close()

    async def test_update_title_not_found(self, httpx_mock):
        """404 returns False."""
        httpx_mock.add_response(
            url="http://backend:8001/api/v1/ai/internal/title-session/missing/",
            method="PATCH",
            status_code=404,
            json={"error": "Session not found"},
        )

        client = CoreApiClient(
            base_url="http://backend:8001",
            worker_token="test-token",
        )

        result = await client.update_title("missing", "Test Title", "tenant-1")
        assert result is False

        await client.close()

    async def test_sends_correct_headers(self, httpx_mock):
        """X-Worker-Token and X-Tenant-ID headers are present."""
        httpx_mock.add_response(
            url="http://backend:8001/api/v1/ai/internal/title-session/abc-123/",
            method="PATCH",
            status_code=200,
            json={"status": "updated"},
        )

        client = CoreApiClient(
            base_url="http://backend:8001",
            worker_token="my-secret-token",
        )

        await client.update_title("abc-123", "Test Title", "tenant-1")

        request = httpx_mock.get_request()
        assert request.headers["x-worker-token"] == "my-secret-token"
        assert request.headers["x-tenant-id"] == "tenant-1"
        assert request.headers["content-type"] == "application/json"

        await client.close()

    async def test_sends_correct_payload(self, httpx_mock):
        """Request body contains the title."""
        httpx_mock.add_response(
            url="http://backend:8001/api/v1/ai/internal/title-session/abc-123/",
            method="PATCH",
            status_code=200,
            json={"status": "updated"},
        )

        client = CoreApiClient(
            base_url="http://backend:8001",
            worker_token="test-token",
        )

        await client.update_title("abc-123", "NVIDIA Analysis", "tenant-1")

        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body == {"title": "NVIDIA Analysis"}

        await client.close()

    async def test_close_when_not_opened(self):
        """Close is safe when client was never used."""
        client = CoreApiClient(
            base_url="http://backend:8001",
            worker_token="test-token",
        )
        await client.close()  # Should not raise
