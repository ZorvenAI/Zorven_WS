"""Tests for the callback client — HTTP PATCH to core-api-service."""

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

    async def test_returns_false_on_http_error(self, httpx_mock):
        httpx_mock.add_response(url=CALLBACK_URL, method="PATCH", status_code=500)

        client = CallbackClient(callback_token=TOKEN)
        result = await client.send_progress(
            CALLBACK_URL,
            progress={"node1": {"status": "running"}},
        )

        assert result is False

    async def test_returns_false_on_connection_error(self, httpx_mock):
        import httpx

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
