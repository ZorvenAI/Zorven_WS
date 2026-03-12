"""Tests for SKL-CIA-12: Human Escalation."""

from unittest.mock import AsyncMock, MagicMock

from app.skills.human_escalation import HumanEscalation
from app.skills.models import SkillContext


def _context():
    return SkillContext(session_id="s1", tenant_id="t1", user_role="EDITOR")


class TestHumanEscalation:
    async def test_meta_skill_id(self):
        skill = HumanEscalation()
        assert skill.meta.skill_id == "SKL-CIA-12"

    async def test_escalation_without_kafka(self):
        skill = HumanEscalation(kafka_producer=None)
        result = await skill.execute(
            {"reason": "Low confidence", "context_summary": "Test", "severity": "high"},
            _context(),
        )
        assert result.success
        assert result.data["escalated"] is True
        assert result.data["severity"] == "high"

    async def test_escalation_with_kafka(self):
        producer = MagicMock()
        producer.send_audit = AsyncMock()
        skill = HumanEscalation(kafka_producer=producer)
        result = await skill.execute(
            {"reason": "Manual review", "context_summary": "Need review"},
            _context(),
        )
        assert result.success
        producer.send_audit.assert_awaited_once()

    async def test_kafka_failure_graceful(self):
        producer = MagicMock()
        producer.send_audit = AsyncMock(side_effect=Exception("Kafka down"))
        skill = HumanEscalation(kafka_producer=producer)
        result = await skill.execute(
            {"reason": "test"}, _context()
        )
        assert result.success  # Graceful on Kafka failure

    async def test_event_contains_tenant_info(self):
        skill = HumanEscalation()
        result = await skill.execute(
            {"reason": "test", "context_summary": "summary"},
            _context(),
        )
        event = result.data["event"]
        assert event["tenant_id"] == "t1"
        assert event["session_id"] == "s1"
