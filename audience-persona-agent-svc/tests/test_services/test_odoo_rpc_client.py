"""Tests for OdooRPCClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.odoo_rpc_client import OdooRPCClient


class TestOdooRPCClient:
    def test_init(self):
        client = OdooRPCClient(
            url="http://odoo:8069",
            db="test_db",
            username="admin",
            password="admin",
        )
        assert client.url == "http://odoo:8069"
        assert client._uid is None

    @patch("app.services.odoo_rpc_client.xmlrpc.client.ServerProxy")
    async def test_authenticate(self, mock_proxy_cls):
        mock_proxy = MagicMock()
        mock_proxy.authenticate.return_value = 2
        mock_proxy_cls.return_value = mock_proxy

        client = OdooRPCClient(
            url="http://odoo:8069", db="db", username="admin", password="pw"
        )
        uid = await client.authenticate()
        assert uid == 2
        assert client._uid == 2

    @patch("app.services.odoo_rpc_client.xmlrpc.client.ServerProxy")
    async def test_authenticate_failure(self, mock_proxy_cls):
        mock_proxy = MagicMock()
        mock_proxy.authenticate.return_value = 0
        mock_proxy_cls.return_value = mock_proxy

        client = OdooRPCClient(
            url="http://odoo:8069", db="db", username="admin", password="pw"
        )
        with pytest.raises(ConnectionError):
            await client.authenticate()

    @patch("app.services.odoo_rpc_client.xmlrpc.client.ServerProxy")
    async def test_search_read(self, mock_proxy_cls):
        # auth proxy
        auth_proxy = MagicMock()
        auth_proxy.authenticate.return_value = 2
        # models proxy
        models_proxy = MagicMock()
        models_proxy.execute_kw.return_value = [{"id": 1, "name": "Test"}]
        mock_proxy_cls.side_effect = [auth_proxy, models_proxy]

        client = OdooRPCClient(
            url="http://odoo:8069", db="db", username="admin", password="pw"
        )
        results = await client.search_read(
            "res.partner", domain=[], fields=["name"], limit=10
        )
        assert len(results) == 1
        assert results[0]["name"] == "Test"

    @patch("app.services.odoo_rpc_client.xmlrpc.client.ServerProxy")
    async def test_search_count(self, mock_proxy_cls):
        auth_proxy = MagicMock()
        auth_proxy.authenticate.return_value = 2
        models_proxy = MagicMock()
        models_proxy.execute_kw.return_value = 42
        mock_proxy_cls.side_effect = [auth_proxy, models_proxy]

        client = OdooRPCClient(
            url="http://odoo:8069", db="db", username="admin", password="pw"
        )
        count = await client.search_count("res.partner")
        assert count == 42
