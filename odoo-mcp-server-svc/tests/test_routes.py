"""Tests for API routes — covers uncovered lines in app/api/routes.py.

Focuses on:
  - _get_client_ip() with X-Forwarded-For, fallback to client.host, and no client
  - /execute rate limiting (429 when denied, 200 when allowed, 200 when no redis)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import _get_client_ip

# ── _get_client_ip ─────────────────────────────────────────────────


class TestGetClientIp:
    """Tests for the _get_client_ip helper function."""

    def test_with_x_forwarded_for_single_ip(self):
        """Returns the single IP from X-Forwarded-For header."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "203.0.113.50"}
        assert _get_client_ip(request) == "203.0.113.50"

    def test_with_x_forwarded_for_multiple_ips(self):
        """Returns the first IP when X-Forwarded-For has multiple."""
        request = MagicMock()
        request.headers = {
            "x-forwarded-for": "203.0.113.50, 70.41.3.18, 150.172.238.178"
        }
        assert _get_client_ip(request) == "203.0.113.50"

    def test_with_x_forwarded_for_whitespace(self):
        """Strips whitespace around the IP."""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "  10.0.0.1  , 10.0.0.2"}
        assert _get_client_ip(request) == "10.0.0.1"

    def test_without_header_falls_back_to_client_host(self):
        """Falls back to request.client.host when no X-Forwarded-For."""
        request = MagicMock()
        request.headers = {}
        request.client.host = "127.0.0.1"
        assert _get_client_ip(request) == "127.0.0.1"

    def test_without_header_and_no_client(self):
        """Returns 'unknown' when no header and client is None."""
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert _get_client_ip(request) == "unknown"


# ── /execute rate limiting ─────────────────────────────────────────


class TestExecuteRateLimiting:
    """Tests for the /execute endpoint's rate limiting logic."""

    @pytest.fixture
    def valid_payload(self) -> dict:
        return {
            "input_prompt": "Search for partners",
            "input_context": {},
            "tenant_context": {},
            "config": {},
            "previous_outputs": {},
        }

    async def test_rate_limit_exceeded_returns_429(self, valid_payload):
        """When redis_manager.check_rate_limit returns False, the
        endpoint returns HTTP 429."""
        mock_redis = AsyncMock()
        mock_redis.check_rate_limit = AsyncMock(return_value=False)

        with patch("app.api.routes.redis_manager", mock_redis):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/execute",
                    json=valid_payload,
                    headers={"X-Tenant-ID": "test-tenant"},
                )

        assert resp.status_code == 429
        assert "Rate limit exceeded" in resp.json()["detail"]

    async def test_rate_limit_allowed_returns_200(self, valid_payload):
        """When redis_manager.check_rate_limit returns True, the
        endpoint returns HTTP 200."""
        mock_redis = AsyncMock()
        mock_redis.check_rate_limit = AsyncMock(return_value=True)

        with patch("app.api.routes.redis_manager", mock_redis):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/execute",
                    json=valid_payload,
                    headers={"X-Tenant-ID": "test-tenant"},
                )

        assert resp.status_code == 200

    async def test_no_redis_manager_returns_200(self, valid_payload):
        """When redis_manager is None, rate limiting is skipped and
        the endpoint returns HTTP 200."""
        with patch("app.api.routes.redis_manager", None):
            from app.main import app

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/execute",
                    json=valid_payload,
                    headers={"X-Tenant-ID": "test-tenant"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
