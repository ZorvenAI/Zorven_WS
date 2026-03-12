"""Tests for SKL-MRA-08: HumanEscalation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.messaging.kafka_producer import AuditProducer
from app.skills.human_escalation import HumanEscalation
from app.skills.models import SkillContext


def _ctx() -> SkillContext:
    return SkillContext(session_id="s1", tenant_id="t1")


class TestHumanEscalation:
    async def test_escalation_succeeds(self):
        producer = MagicMock(spec=AuditProducer)
        producer.send_audit = AsyncMock()
        skill = HumanEscalation(audit_producer=producer)
        result = await skill.execute(
            {"reason": "Low confidence", "severity": "high"}, _ctx()
        )
        assert result.success
        assert result.data["status"] == "escalated"
        assert result.data["severity"] == "high"
        assert "escalation_id" in result.data
        producer.send_audit.assert_awaited_once()

    async def test_escalation_without_producer(self):
        skill = HumanEscalation(audit_producer=None)
        result = await skill.execute({"reason": "Test"}, _ctx())
        assert result.success

    async def test_meta_correct(self):
        skill = HumanEscalation()
        assert skill.meta.skill_id == "SKL-MRA-08"
        assert "VIEWER" in skill.meta.allowed_roles
        assert skill.meta.idempotent is False
