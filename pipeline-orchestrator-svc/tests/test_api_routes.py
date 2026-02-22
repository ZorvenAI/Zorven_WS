"""Tests for API routes — Phase 1 contract validation."""

from unittest.mock import AsyncMock, patch


class TestHealthEndpoint:
    """GET /health — no auth required."""

    async def test_health_returns_ok(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestDispatchEndpoint:
    """POST /v1/jobs/dispatch — accepts jobs for execution."""

    async def test_dispatch_returns_202(
        self, client, valid_dispatch_payload, service_token_headers
    ):
        response = await client.post(
            "/v1/jobs/dispatch",
            json=valid_dispatch_payload,
            headers=service_token_headers,
        )
        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}

    async def test_dispatch_without_manifest(
        self, client, valid_dispatch_payload, service_token_headers
    ):
        """Auto-detect mode: manifest is null, available_manifests provided."""
        valid_dispatch_payload["manifest"] = None
        valid_dispatch_payload["available_manifests"] = [
            {
                "pipeline_id": "brand-analysis",
                "name": "Brand Analysis",
                "description": "Analyze brand positioning",
            },
        ]
        response = await client.post(
            "/v1/jobs/dispatch",
            json=valid_dispatch_payload,
            headers=service_token_headers,
        )
        assert response.status_code == 202

    async def test_dispatch_invalid_token_returns_403(
        self, client, valid_dispatch_payload
    ):
        response = await client.post(
            "/v1/jobs/dispatch",
            json=valid_dispatch_payload,
            headers={"X-Service-Token": "wrong-token"},
        )
        assert response.status_code == 403

    async def test_dispatch_missing_token_returns_403(
        self, client, valid_dispatch_payload
    ):
        response = await client.post(
            "/v1/jobs/dispatch",
            json=valid_dispatch_payload,
        )
        assert response.status_code == 403

    async def test_dispatch_malformed_body_returns_422(
        self, client, service_token_headers
    ):
        response = await client.post(
            "/v1/jobs/dispatch",
            json={"bad": "data"},
            headers=service_token_headers,
        )
        assert response.status_code == 422

    async def test_dispatch_missing_required_fields_returns_422(
        self, client, service_token_headers
    ):
        response = await client.post(
            "/v1/jobs/dispatch",
            json={"job_id": "123"},  # Missing input_prompt, callback_url
            headers=service_token_headers,
        )
        assert response.status_code == 422

    async def test_dispatch_invalid_node_type_returns_422(
        self, client, service_token_headers
    ):
        payload = {
            "job_id": "test-123",
            "manifest": {
                "nodes": [{"id": "n1", "type": "unknown_type"}],
                "edges": [],
            },
            "input_prompt": "test",
            "callback_url": "http://example.com/callback",
        }
        response = await client.post(
            "/v1/jobs/dispatch",
            json=payload,
            headers=service_token_headers,
        )
        assert response.status_code == 422


class TestCancelEndpoint:
    """POST /v1/jobs/{job_id}/cancel — cancels a running job."""

    @patch("app.api.routes.get_redis")
    async def test_cancel_returns_200(
        self, mock_get_redis, client, service_token_headers
    ):
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        response = await client.post(
            "/v1/jobs/test-job-id/cancel",
            headers=service_token_headers,
        )
        assert response.status_code == 200
        assert response.json() == {"status": "cancelled"}
        mock_redis.set.assert_called_once()

    async def test_cancel_invalid_token_returns_403(self, client):
        response = await client.post(
            "/v1/jobs/test-job-id/cancel",
            headers={"X-Service-Token": "wrong-token"},
        )
        assert response.status_code == 403
