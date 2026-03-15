"""Tests for SKL-VoCA-01: Odoo Helpdesk Ticket Extractor."""

import pytest
from unittest.mock import AsyncMock

from app.registry.models import hash_customer_id
from app.skills.odoo_helpdesk_extractor import OdooHelpdeskExtractor
from app.skills.models import SkillContext


@pytest.fixture
def extractor(mock_odoo_client, mock_redis_manager):
    """OdooHelpdeskExtractor with mocked dependencies."""
    return OdooHelpdeskExtractor(
        odoo_client=mock_odoo_client,
        redis_manager=mock_redis_manager,
    )


@pytest.mark.unit
def test_meta_attributes(extractor):
    """Skill meta has correct ID and name."""
    assert extractor.meta.skill_id == "SKL-VoCA-01"
    assert extractor.meta.name == "odoo_helpdesk_extractor"
    assert "VIEWER" not in extractor.meta.allowed_roles
    assert "EDITOR" in extractor.meta.allowed_roles


@pytest.mark.asyncio
@pytest.mark.unit
async def test_execute_returns_tickets(
    extractor, mock_odoo_client, mock_redis_manager
):
    """Skill returns tickets when Odoo returns data."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="test-tenant",
        user_role="EDITOR",
        operating_mode="full",
    )
    mock_redis_manager.get_odoo_cache = AsyncMock(return_value=None)
    mock_redis_manager.get_tenant_config = AsyncMock(return_value=None)
    mock_odoo_client.search_read = AsyncMock(
        return_value=[
            {
                "id": 101,
                "name": "Ticket: Login Issue",
                "description": "User cannot login to dashboard",
                "partner_id": [42, "Acme Corp"],
                "priority": "2",
                "stage_id": [1, "New"],
                "create_date": "2025-12-01 10:00:00",
            },
            {
                "id": 102,
                "name": "Ticket: Billing Error",
                "description": "Invoice amount incorrect",
                "partner_id": [43, "Beta Inc"],
                "priority": "1",
                "stage_id": [2, "In Progress"],
                "create_date": "2025-12-02 14:00:00",
            },
        ]
    )
    result = await extractor.execute(
        {"prompt": "analyze", "limit": 100}, ctx
    )
    assert result.success is True
    assert result.skill_id == "SKL-VoCA-01"
    assert result.data["ticket_count"] == 2
    assert len(result.data["tickets"]) == 2
    # Verify customer IDs are hashed
    for ticket in result.data["tickets"]:
        assert "customer_id_hash" in ticket
        if ticket["customer_id_hash"]:
            assert len(ticket["customer_id_hash"]) == 64  # SHA-256 hex


@pytest.mark.asyncio
@pytest.mark.unit
async def test_customer_id_hashed(
    extractor, mock_odoo_client, mock_redis_manager
):
    """Customer IDs are SHA-256 hashed (Decision #5)."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="test-tenant",
        user_role="EDITOR",
        operating_mode="full",
    )
    mock_redis_manager.get_odoo_cache = AsyncMock(return_value=None)
    mock_redis_manager.get_tenant_config = AsyncMock(return_value=None)
    mock_odoo_client.search_read = AsyncMock(
        return_value=[
            {
                "id": 200,
                "name": "Test Ticket",
                "description": "Test description",
                "partner_id": [99, "HashTest Corp"],
                "priority": "1",
                "stage_id": [1, "Open"],
                "create_date": "2025-12-10 09:00:00",
            }
        ]
    )
    result = await extractor.execute({"prompt": "test"}, ctx)
    assert result.success is True
    ticket = result.data["tickets"][0]
    expected_hash = hash_customer_id(99, salt="test-tenant")
    assert ticket["customer_id_hash"] == expected_hash
    # Verify store_hash_lookup was called
    mock_redis_manager.store_hash_lookup.assert_called()
