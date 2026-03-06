"""Tests for the callback client — HTTP PATCH to core-api-service."""

from unittest.mock import AsyncMock

from app.services.callback_client import CallbackClient

CALLBACK_URL = "http://backend:8001/api/v1/orchestration/jobs/test-123/callback/"
TOKEN = "test-callback-token"


class TestCallbackClient:
    """Test PATCH calls, headers, and payloads."""

    async def test_send_progress(self, httpx_mock):
        httpx_mock.add_response(
            url=CALLBACK_URL,
            method="PATCH",
            json={"status": "ok"},
        )

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={"node1": {"status": "running"}},
        )

        assert result is True
        request = httpx_mock.get_request()
        assert request.headers["X-Callback-Token"] == TOKEN
        assert request.headers["Content-Type"] == "application/json"

    async def test_send_completed(self, httpx_mock):
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_completed(
            CALLBACK_URL,
            result_data={"summary": "Done", "findings": []},
            progress={"node1": {"status": "done"}},
        )

        assert result is True
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["status"] == "completed"
        assert "result_data" in body
        assert "progress" in body

    async def test_send_failed(self, httpx_mock):
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_failed(
            CALLBACK_URL,
            error_message="Something went wrong",
            progress={"node1": {"status": "failed"}},
        )

        assert result is True
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["status"] == "failed"
        assert body["error_message"] == "Something went wrong"

    async def test_send_running(self, httpx_mock):
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_running(
            CALLBACK_URL,
            progress={"node1": {"status": "pending"}},
        )

        assert result is True
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["status"] == "running"

    async def test_send_resolved_manifest(self, httpx_mock):
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_resolved_manifest(
            CALLBACK_URL,
            manifest_id="brand-analysis",
            progress={"router": {"status": "done"}},
        )

        assert result is True
        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert body["resolved_manifest_id"] == "brand-analysis"
        assert "progress" in body

    async def test_returns_false_on_5xx(self, httpx_mock, monkeypatch):
        # Patch asyncio.sleep to avoid real delays in CI
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        # 5xx is retried, so provide responses for all 4 attempts
        for _ in range(4):
            httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", status_code=500)

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={"node1": {"status": "running"}},
        )

        assert result is False
        assert len(httpx_mock.get_requests()) == 4

    async def test_returns_false_on_connection_error(self, httpx_mock, monkeypatch):
        import httpx

        # Patch asyncio.sleep to avoid real delays in CI
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        # Transport errors are retried, so provide exceptions for all 4 attempts
        for _ in range(4):
            httpx_mock.add_exception(
                httpx.ConnectError("Connection refused"),
                url=CALLBACK_URL,
            )

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={},
        )

        assert result is False
        assert len(httpx_mock.get_requests()) == 4

    async def test_retries_transport_error_then_succeeds(self, httpx_mock, monkeypatch):
        """Transport error on first attempt, success on retry."""
        import httpx

        # Patch asyncio.sleep to avoid real delays in CI
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        httpx_mock.add_exception(
            httpx.ConnectError("Connection reset"),
            url=CALLBACK_URL,
        )
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={"n1": {"status": "running"}},
        )

        assert result is True
        assert len(httpx_mock.get_requests()) == 2

    async def test_retries_5xx_then_succeeds(self, httpx_mock, monkeypatch):
        """5xx on first attempt, success on retry."""
        # Patch asyncio.sleep to avoid real delays in CI
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", status_code=502)
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={"n1": {"status": "running"}},
        )

        assert result is True
        assert len(httpx_mock.get_requests()) == 2

    async def test_no_retry_on_4xx(self, httpx_mock):
        """4xx errors are deterministic and must NOT be retried."""
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", status_code=403)

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={"n1": {"status": "running"}},
        )

        assert result is False
        assert len(httpx_mock.get_requests()) == 1

    async def test_error_message_truncated_to_10000(self, httpx_mock):
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", json={})

        client = CallbackClient(callback_token=TOKEN)
        long_error = "x" * 20000
        await client.send_failed(
            CALLBACK_URL,
            error_message=long_error,
            progress={},
        )

        request = httpx_mock.get_request()
        import json

        body = json.loads(request.content)
        assert len(body["error_message"]) == 10000
