"""Tests for OdooRPCClient."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.odoo_rpc_client import OdooRPCClient


@pytest.mark.asyncio
@pytest.mark.unit
async def test_search_read_returns_list():
    """search_read returns a list of records from XML-RPC."""
    client = OdooRPCClient(
        url="http://localhost:8069",
        db="testdb",
        username="admin",
        password="admin",
    )

    # Mock authentication and XML-RPC calls
    client._uid = 2
    mock_models = MagicMock()

    expected_records = [
        {"id": 1, "name": "Ticket A", "priority": "1"},
        {"id": 2, "name": "Ticket B", "priority": "2"},
    ]
    mock_models.execute_kw = MagicMock(return_value=expected_records)
    client._models = mock_models

    with patch("asyncio.get_event_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(
            return_value=expected_records
        )

        result = await client.search_read(
            model="project.task",
            domain=[],
            fields=["id", "name", "priority"],
            limit=100,
        )

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "Ticket A"
    assert result[1]["name"] == "Ticket B"
