"""Tests for BSAContextLoader."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.context_loader import BSAContextLoader


@pytest.fixture
def loader():
    """Create context loader."""
    return BSAContextLoader()


class TestBSAContextLoader:
    """Test BSAContextLoader."""

    async def test_load_all_returns_dict(self, loader):
        """load_all should return dict with all context keys."""
        with patch.object(loader, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"data": "test"}

            result = await loader.load_all("test-tenant")

            assert "wf1" in result
            assert "bpa" in result
            assert "bpv" in result
            assert "nta" in result
            assert "company" in result

    async def test_load_all_handles_failures(self, loader):
        """load_all should handle individual endpoint failures gracefully."""
        with patch.object(loader, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection refused")

            result = await loader.load_all("test-tenant")

            # All contexts should be None on failure (return_exceptions=True)
            assert result["wf1"] is None
            assert result["bpa"] is None
            assert result["bpv"] is None
            assert result["nta"] is None
            assert result["company"] is None

    async def test_load_wf1_calls_correct_endpoint(self, loader):
        """load_wf1 should call the wf1-context endpoint."""
        with patch.object(loader, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"discoveries": []}

            await loader.load_wf1("test-tenant")

            mock_get.assert_awaited_once()
            call_args = mock_get.call_args
            assert "wf1-context" in str(call_args)

    async def test_load_nta_calls_correct_endpoint(self, loader):
        """load_nta should call the nta-context endpoint."""
        with patch.object(loader, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"naming_brief": {}}

            await loader.load_nta("test-tenant")

            mock_get.assert_awaited_once()
            call_args = mock_get.call_args
            assert "nta-context" in str(call_args)

    async def test_load_all_makes_parallel_calls(self, loader):
        """load_all should call 5 endpoints."""
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return {"data": f"context-{call_count}"}

        with patch.object(loader, "_get", side_effect=mock_get):
            await loader.load_all("test-tenant")

        assert call_count == 5
