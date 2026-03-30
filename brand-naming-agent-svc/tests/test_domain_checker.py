"""Tests for DomainChecker (SKL-NTA-06)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import dns.asyncresolver
import pytest

from app.logic.domain_checker import DomainChecker


@pytest.fixture
def checker():
    return DomainChecker()


class TestDomainChecker:
    """Test DNS lookup domain availability checking."""

    @patch("dns.asyncresolver.Resolver")
    async def test_domain_taken_returns_false(self, MockResolver, checker):
        """Domain that resolves → False (taken)."""
        mock_resolver = MockResolver.return_value
        mock_resolver.lifetime = 5.0
        mock_resolver.resolve = AsyncMock(return_value=["1.2.3.4"])

        result = await checker._check_domain("google.com")
        assert result is False

    @patch("dns.asyncresolver.Resolver")
    async def test_domain_available_returns_true(self, MockResolver, checker):
        """NXDOMAIN → True (available)."""
        mock_resolver = MockResolver.return_value
        mock_resolver.lifetime = 5.0
        mock_resolver.resolve = AsyncMock(
            side_effect=dns.asyncresolver.NXDOMAIN()
        )

        result = await checker._check_domain("xyznonexistent12345.com")
        assert result is True

    @patch("dns.asyncresolver.Resolver")
    async def test_noanswer_returns_true(self, MockResolver, checker):
        """NoAnswer → True (likely available)."""
        mock_resolver = MockResolver.return_value
        mock_resolver.lifetime = 5.0
        mock_resolver.resolve = AsyncMock(
            side_effect=dns.asyncresolver.NoAnswer()
        )

        result = await checker._check_domain("test.com")
        assert result is True

    async def test_check_multiple_tlds(self, checker):
        """check() iterates over provided TLDs."""
        checker._check_domain = AsyncMock(
            side_effect=[True, False, None]
        )
        result = await checker.check("testbrand", tlds=[".com", ".io", ".co"])
        assert result == {".com": True, ".io": False, ".co": None}
        assert checker._check_domain.call_count == 3

    @patch("dns.asyncresolver.Resolver")
    async def test_timeout_returns_none(self, MockResolver, checker):
        """Timeout should return None."""
        mock_resolver = MockResolver.return_value
        mock_resolver.lifetime = 5.0
        mock_resolver.resolve = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        result = await checker._check_domain("slow.example.com")
        assert result is None

    @patch("dns.asyncresolver.Resolver")
    async def test_no_nameservers_returns_none(self, MockResolver, checker):
        """NoNameservers → None."""
        import dns.resolver

        mock_resolver = MockResolver.return_value
        mock_resolver.lifetime = 5.0
        mock_resolver.resolve = AsyncMock(
            side_effect=dns.resolver.NoNameservers(
                request=MagicMock(), errors=[],
            )
        )

        result = await checker._check_domain("broken.com")
        assert result is None
