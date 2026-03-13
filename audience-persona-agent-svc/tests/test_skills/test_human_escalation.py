"""Tests for SKL-APA-12: Human Escalation."""

from unittest.mock import AsyncMock

from app.skills.human_escalation import HumanEscalation
from app.skills.models import SkillContext


def _ctx():
    return SkillContext(session_id="s", tenant_id="t", user_role="EDITOR")


class TestHumanEscalation:
    async def test_meta(self):
        skill = HumanEscalation()
        assert skill.meta.skill_id == "SKL-APA-12"
        assert skill.meta.circuit_breaker_dependency == "kafka"
        assert "VIEWER" in skill.meta.allowed_roles

    async def test_execute_with_kafka(self):
        mock_producer = AsyncMock()
        skill = HumanEscalation(kafka_producer=mock_producer)
        result = await skill.execute(
            {
                "reason": "Low confidence",
                "context_summary": "Persona analysis had 0.2 confidence",
                "severity": "high",
            },
            _ctx(),
        )
        assert result.success is True
        assert result.data["escalated"] is True
        assert result.data["reason"] == "Low confidence"
        assert result.data["severity"] == "high"
        mock_producer.send_event.assert_called_once()
        event = mock_producer.send_event.call_args[0][0]
        assert event["type"] == "audience_persona.escalation"
        assert event["tenant_id"] == "t"

    async def test_execute_without_kafka(self):
        skill = HumanEscalation(kafka_producer=None)
        result = await skill.execute(
            {"reason": "RBAC escalation", "severity": "medium"},
            _ctx(),
        )
        assert result.success is True
        assert result.data["escalated"] is True

    async def test_defaults(self):
        skill = HumanEscalation()
        result = await skill.execute({}, _ctx())
        assert result.success is True
        assert result.data["reason"] == "Automated escalation"
        assert result.data["severity"] == "medium"

    async def test_kafka_failure_graceful(self):
        mock_producer = AsyncMock()
        mock_producer.send_event.side_effect = Exception("Kafka down")
        skill = HumanEscalation(kafka_producer=mock_producer)
        result = await skill.execute({"reason": "test", "severity": "low"}, _ctx())
        assert result.success is True
        assert result.data["escalated"] is True
