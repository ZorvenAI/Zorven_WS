"""Tests for SKL-VoCA-03: Odoo CRM Chatter Extractor."""

import pytest
from unittest.mock import AsyncMock

from app.skills.odoo_chatter_extractor import OdooChatterExtractor
from app.skills.models import SkillContext


@pytest.fixture
def extractor(mock_odoo_client, mock_redis_manager):
    """OdooChatterExtractor with mocked dependencies."""
    return OdooChatterExtractor(
        odoo_client=mock_odoo_client,
        redis_manager=mock_redis_manager,
    )


@pytest.mark.unit
def test_meta_attributes(extractor):
    """Skill meta has correct ID and name."""
    assert extractor.meta.skill_id == "SKL-VoCA-03"
    assert extractor.meta.name == "odoo_chatter_extractor"
    assert "VIEWER" not in extractor.meta.allowed_roles
    assert "EDITOR" in extractor.meta.allowed_roles


@pytest.mark.asyncio
@pytest.mark.unit
async def test_filters_internal_notes(
    extractor, mock_odoo_client, mock_redis_manager
):
    """Internal notes (message_type='notification') are filtered out.

    The skill only keeps 'email' and 'comment' message types that
    pass the _is_customer_message check.
    """
    ctx = SkillContext(
        session_id="s1",
        tenant_id="test-tenant",
        user_role="EDITOR",
        operating_mode="full",
    )
    mock_redis_manager.get_odoo_cache = AsyncMock(return_value=None)

    # Return a mix of customer and internal messages
    mock_odoo_client.search_read = AsyncMock(
        return_value=[
            {
                "id": 1,
                "body": "<p>Customer complaint about billing</p>",
                "author_id": [10, "Customer A"],
                "date": "2025-12-01 09:00:00",
                "message_type": "email",
                "res_id": 100,
                "model": "crm.lead",
                "subject": "Billing Issue",
            },
            {
                "id": 2,
                "body": "<p>Internal staff note</p>",
                "author_id": False,
                "date": "2025-12-01 10:00:00",
                "message_type": "comment",
                "res_id": 100,
                "model": "crm.lead",
                "subject": "",
            },
            {
                "id": 3,
                "body": "<p>Follow-up from customer</p>",
                "author_id": [11, "Customer B"],
                "date": "2025-12-02 09:00:00",
                "message_type": "comment",
                "res_id": 101,
                "model": "crm.lead",
                "subject": "RE: Support",
            },
        ]
    )

    result = await extractor.execute({"prompt": "chatter analysis"}, ctx)
    assert result.success is True

    # Message with author_id=False and message_type='comment' is filtered
    # as _is_customer_message returns False for empty author_id
    feedback = result.data["feedback"]
    # We should have messages from 3 models (crm.lead, sale.order, res.partner)
    # but all use the same mock return value. We expect the internal note
    # (id=2, author_id=False) to be filtered out for each model.
    email_msgs = [fb for fb in feedback if fb["message_type"] == "email"]
    assert len(email_msgs) > 0  # email type always passes
    # Internal note with no author should not be present
    no_author = [fb for fb in feedback if fb["customer_id_hash"] == ""]
    # Messages with no author_id (False) are filtered by _is_customer_message
    # so there should be no empty-hash chatter messages that are "comment" type
    for fb in feedback:
        if fb["message_type"] == "comment":
            assert fb["customer_id_hash"] != "", (
                "Comment messages without author should be filtered"
            )
