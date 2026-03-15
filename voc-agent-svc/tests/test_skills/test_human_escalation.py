"""Tests for SKL-VoCA-14: Human Escalation."""

import pytest
from unittest.mock import AsyncMock

from app.skills.human_escalation import HumanEscalation
from app.skills.models import SkillContext


@pytest.fixture
def escalation():
    """HumanEscalation with mocked audit producer."""
    mock_audit = AsyncMock()
    mock_audit.send_event = AsyncMock()
    return HumanEscalation(audit_producer=mock_audit)


@pytest.mark.unit
def test_meta_attributes(escalation):
    """Skill meta has correct ID and name."""
    assert escalation.meta.skill_id == "SKL-VoCA-14"
    assert escalation.meta.name == "human_escalation"
    assert "VIEWER" in escalation.meta.allowed_roles
    assert escalation.meta.idempotent is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_critical_sentiment_escalation(escalation):
    """Escalation with critical negative sentiment trigger."""
    ctx = SkillContext(
        session_id="s1",
        tenant_id="test-tenant",
        user_role="EDITOR",
        operating_mode="external_only",
    )
    result = await escalation.execute(
        {
            "reason": "Critical negative sentiment detected",
            "severity": "critical",
            "trigger_type": "critical_negative_sentiment",
            "sentiment": {
                "positive": 0.1,
                "neutral": 0.2,
                "negative": 0.7,
            },
            "context_summary": "70% negative sentiment across all channels",
        },
        ctx,
    )
    assert result.success is True
    assert result.data["escalated"] is True
    assert result.data["severity"] == "critical"
    assert result.data["trigger_type"] == "critical_negative_sentiment"
    assert result.data["emitted"] is True
    # Verify audit producer was called
    escalation._audit.send_event.assert_called_once()
