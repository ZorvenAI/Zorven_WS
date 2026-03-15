"""Tests for SKL-VoCA-04: Odoo Customer Segment Linker."""

import pytest

from app.skills.odoo_customer_segment_linker import OdooCustomerSegmentLinker
from app.skills.models import SkillContext


@pytest.fixture
def linker():
    """OdooCustomerSegmentLinker instance."""
    return OdooCustomerSegmentLinker()


@pytest.mark.unit
def test_meta_attributes(linker):
    """Skill meta has correct ID and name."""
    assert linker.meta.skill_id == "SKL-VoCA-04"
    assert linker.meta.name == "odoo_customer_segment_linker"
    assert "VIEWER" in linker.meta.allowed_roles
    assert linker.meta.idempotent is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_links_feedback_to_personas(linker):
    """Skill links feedback items to APA persona segments."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="test-tenant",
        user_role="EDITOR",
        previous_outputs={
            "audience_persona": {
                "personas": [
                    {
                        "slug": "enterprise-buyer",
                        "segment_label": "Enterprise Buyer",
                        "customer_id_hashes": ["abc123hash"],
                        "industries": ["SaaS"],
                        "pain_points": ["Cost"],
                    },
                    {
                        "slug": "smb-owner",
                        "segment_label": "SMB Owner",
                        "customer_id_hashes": ["xyz789hash"],
                        "industries": ["Retail"],
                        "pain_points": ["Complexity"],
                    },
                ],
            },
        },
        operating_mode="full",
    )

    input_data = {
        "feedback": [
            {
                "feedback_id": "fb-001",
                "customer_id_hash": "abc123hash",
                "metadata": {},
            },
            {
                "feedback_id": "fb-002",
                "customer_id_hash": "unknown-hash",
                "metadata": {"industry": "Retail"},
            },
            {
                "feedback_id": "fb-003",
                "customer_id_hash": "",
                "metadata": {},
            },
        ],
    }

    result = await linker.execute(input_data, ctx)
    assert result.success is True
    assert result.data["linked_count"] >= 2
    # Direct hash match should have highest confidence
    linked = result.data["linked_feedback"]
    direct_match = [lf for lf in linked if lf["linking_method"] == "direct_hash_match"]
    assert len(direct_match) >= 1
    assert direct_match[0]["confidence"] == 0.95
