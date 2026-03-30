"""Tests for CAAContextLoader."""

from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from app.services.context_loader import CAAContextLoader


class TestCAAContextLoader:
    """Test the HTTP context loader."""

    async def test_load_all_parallel_calls(self):
        """load_all returns all 7 context slots."""
        loader = CAAContextLoader()
        with (
            patch.object(loader, "_get", new_callable=AsyncMock) as mock_get,
            patch.object(loader, "load_odoo", new_callable=AsyncMock) as mock_odoo,
            patch.object(
                loader, "load_rag_learnings", new_callable=AsyncMock
            ) as mock_rag,
        ):
            mock_get.return_value = {"data": True}
            mock_odoo.return_value = None
            mock_rag.return_value = None

            result = await loader.load_all("test-tenant")

            assert "wf1" in result
            assert "bpa" in result
            assert "wf2_chain" in result
            assert "company" in result
            assert "baa" in result
            assert "odoo" in result
            assert "rag" in result

    async def test_load_all_optional_services_fail_gracefully(self):
        """When Odoo or RAG raise exceptions, load_all returns None for them."""
        loader = CAAContextLoader()
        with (
            patch.object(loader, "_get", new_callable=AsyncMock) as mock_get,
            patch.object(loader, "load_odoo", new_callable=AsyncMock) as mock_odoo,
            patch.object(
                loader, "load_rag_learnings", new_callable=AsyncMock
            ) as mock_rag,
        ):
            mock_get.return_value = {"data": True}
            mock_odoo.side_effect = Exception("Odoo down")
            mock_rag.side_effect = Exception("RAG down")

            result = await loader.load_all("test-tenant")

            # Exceptions are caught by asyncio.gather(return_exceptions=True)
            assert result["odoo"] is None
            assert result["rag"] is None

    @patch("app.services.context_loader.httpx.AsyncClient")
    async def test_load_wf1_success(self, mock_client_cls):
        """load_wf1 returns parsed JSON on 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"market_research": {}, "industry": "SaaS"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        loader = CAAContextLoader()
        result = await loader.load_wf1("test-tenant")
        assert result == {"market_research": {}, "industry": "SaaS"}

    @patch("app.services.context_loader.httpx.AsyncClient")
    async def test_load_company_success(self, mock_client_cls):
        """load_company returns parsed JSON on 200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"name": "Acme", "industry": "Tech"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        loader = CAAContextLoader()
        result = await loader.load_company("test-tenant")
        assert result["name"] == "Acme"

    @patch("app.services.context_loader.settings")
    async def test_load_odoo_disabled_when_no_url(self, mock_settings):
        """load_odoo returns None when ODOO_MCP_URL is empty."""
        mock_settings.ODOO_MCP_URL = ""
        loader = CAAContextLoader()
        result = await loader.load_odoo("test-tenant")
        assert result is None

    @patch("app.services.context_loader.settings")
    async def test_load_rag_disabled_when_no_store_id(self, mock_settings):
        """load_rag_learnings returns None when RAG_DATA_STORE_ID is empty."""
        mock_settings.RAG_DATA_STORE_ID = ""
        loader = CAAContextLoader()
        result = await loader.load_rag_learnings("test-tenant")
        assert result is None
