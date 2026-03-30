"""Tests for NTAContextLoader."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.context_loader import NTAContextLoader


@pytest.fixture
def loader():
    return NTAContextLoader()


class TestLoadAll:
    """Test parallel context loading."""

    @patch.object(NTAContextLoader, "load_wf1", new_callable=AsyncMock)
    @patch.object(NTAContextLoader, "load_bpa", new_callable=AsyncMock)
    @patch.object(NTAContextLoader, "load_bpv", new_callable=AsyncMock)
    @patch.object(NTAContextLoader, "load_company", new_callable=AsyncMock)
    async def test_load_all_returns_all_contexts(
        self, mock_company, mock_bpv, mock_bpa, mock_wf1, loader
    ):
        mock_wf1.return_value = {"mra": {}}
        mock_bpa.return_value = {"positioning": {}}
        mock_bpv.return_value = {"personality": {}}
        mock_company.return_value = {"name": "TestCo"}

        result = await loader.load_all("test-tenant")

        assert result["wf1"] == {"mra": {}}
        assert result["bpa"] == {"positioning": {}}
        assert result["bpv"] == {"personality": {}}
        assert result["company"] == {"name": "TestCo"}

    @patch.object(NTAContextLoader, "load_wf1", new_callable=AsyncMock)
    @patch.object(NTAContextLoader, "load_bpa", new_callable=AsyncMock)
    @patch.object(NTAContextLoader, "load_bpv", new_callable=AsyncMock)
    @patch.object(NTAContextLoader, "load_company", new_callable=AsyncMock)
    async def test_load_all_handles_exceptions(
        self, mock_company, mock_bpv, mock_bpa, mock_wf1, loader
    ):
        """If a loader raises, its slot should be None."""
        mock_wf1.side_effect = RuntimeError("WF1 down")
        mock_bpa.return_value = {"data": True}
        mock_bpv.side_effect = httpx.TimeoutException("timeout")
        mock_company.return_value = None

        result = await loader.load_all("test-tenant")

        assert result["wf1"] is None
        assert result["bpa"] == {"data": True}
        assert result["bpv"] is None
        assert result["company"] is None


class TestIndividualLoaders:
    """Test individual context endpoints."""

    @patch("app.services.context_loader.httpx.AsyncClient")
    async def test_load_wf1_success(self, MockClient, loader):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"mra": {"market": True}}

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await loader.load_wf1("test-tenant")
        assert result == {"mra": {"market": True}}

    @patch("app.services.context_loader.httpx.AsyncClient")
    async def test_load_returns_none_on_404(self, MockClient, loader):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await loader.load_bpa("test-tenant")
        assert result is None

    @patch("app.services.context_loader.httpx.AsyncClient")
    async def test_load_returns_none_on_500(self, MockClient, loader):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await loader.load_bpv("test-tenant")
        assert result is None

    @patch("app.services.context_loader.httpx.AsyncClient")
    async def test_load_returns_none_on_exception(self, MockClient, loader):
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client_instance.__aenter__ = AsyncMock(
            return_value=mock_client_instance
        )
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client_instance

        result = await loader.load_company("test-tenant")
        assert result is None
