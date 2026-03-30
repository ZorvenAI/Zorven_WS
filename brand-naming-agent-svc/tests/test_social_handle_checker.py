"""Tests for SocialHandleChecker (SKL-NTA-07)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.logic.social_handle_checker import SocialHandleChecker


@pytest.fixture
def checker():
    return SocialHandleChecker()


class TestSocialHandleChecker:
    """Test HTTP HEAD social handle availability."""

    @patch("app.logic.social_handle_checker.httpx.AsyncClient")
    async def test_handle_taken_returns_false(self, MockClient, checker):
        """HTTP 200 → False (handle taken)."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        mock_instance = AsyncMock()
        mock_instance.head = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await checker._check_handle("twitter", "google")
        assert result is False

    @patch("app.logic.social_handle_checker.httpx.AsyncClient")
    async def test_handle_available_returns_true(self, MockClient, checker):
        """HTTP 404 → True (handle available)."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 404

        mock_instance = AsyncMock()
        mock_instance.head = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await checker._check_handle("instagram", "xyznonexistent999")
        assert result is True

    @patch("app.logic.social_handle_checker.httpx.AsyncClient")
    async def test_ambiguous_status_returns_none(self, MockClient, checker):
        """HTTP 302/403 → None (ambiguous)."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 403

        mock_instance = AsyncMock()
        mock_instance.head = AsyncMock(return_value=mock_resp)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await checker._check_handle("linkedin", "test")
        assert result is None

    async def test_unknown_platform_returns_none(self, checker):
        """Unknown platform has no URL template → None."""
        result = await checker._check_handle("tiktok", "test")
        assert result is None

    @patch("app.logic.social_handle_checker.httpx.AsyncClient")
    async def test_timeout_returns_none(self, MockClient, checker):
        """Timeout → None."""
        mock_instance = AsyncMock()
        mock_instance.head = AsyncMock(
            side_effect=httpx.TimeoutException("timeout")
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance

        result = await checker._check_handle("twitter", "test")
        assert result is None

    async def test_check_multiple_platforms(self, checker):
        """check() iterates over provided platforms."""
        checker._check_handle = AsyncMock(
            side_effect=[True, False, None]
        )
        result = await checker.check(
            "testbrand", platforms=["twitter", "instagram", "linkedin"]
        )
        assert result == {"twitter": True, "instagram": False, "linkedin": None}
