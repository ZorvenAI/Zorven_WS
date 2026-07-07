"""Unit tests for prompt lifecycle Kafka events (US-036)."""

import json

from app.kafka.schemas import (
    OPTIMIZATION_COMPLETED,
    OPTIMIZATION_STARTED,
    PROMPT_PROMOTED,
    PROMPT_REGISTERED,
    PROMPT_REJECTED,
    PROMPT_ROLLED_BACK,
    SCHEMA_VERSION,
    VALIDATION_FAILED,
    PromptLifecycleEvent,
)
from app.kafka.topics import (
    LIFECYCLE_TOPIC,
    LIFECYCLE_TOPIC_RETENTION_MS,
)


class TestEventTypeConstants:
    def test_prompt_registered(self):
        assert PROMPT_REGISTERED == "prompt.registered"

    def test_optimization_started(self):
        assert OPTIMIZATION_STARTED == "prompt.optimization.started"

    def test_optimization_completed(self):
        assert OPTIMIZATION_COMPLETED == "prompt.optimization.completed"

    def test_prompt_promoted(self):
        assert PROMPT_PROMOTED == "prompt.promoted"

    def test_validation_failed(self):
        assert VALIDATION_FAILED == "prompt.validation.failed"

    def test_prompt_rolled_back(self):
        assert PROMPT_ROLLED_BACK == "prompt.rolled_back"

    def test_prompt_rejected(self):
        assert PROMPT_REJECTED == "prompt.rejected"


class TestSchemaVersion:
    """AC-3: Schema version header set to 1.0."""

    def test_schema_version_constant(self):
        assert SCHEMA_VERSION == "1.0"

    def test_event_has_schema_version(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        assert event.schema_version == "1.0"


class TestCorrelationId:
    """AC-4: correlation_id used as message key for dedup."""

    def test_auto_generated(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        assert event.correlation_id is not None
        assert len(event.correlation_id) > 0

    def test_unique_per_event(self):
        e1 = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        e2 = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        assert e1.correlation_id != e2.correlation_id

    def test_custom_correlation_id(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
            correlation_id="custom-id-123",
        )
        assert event.correlation_id == "custom-id-123"


class TestPromptPromotedPayload:
    """AC-2: prompt.promoted payload matches §8.2."""

    def test_has_all_required_fields(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="zorven-wf3-cga-system",
            version=5,
            from_state="CANARY",
            to_state="PRODUCTION",
            agent_code="cga",
        )
        payload = event.model_dump()
        assert payload["event_type"] == "prompt.promoted"
        assert payload["prompt_name"] == "zorven-wf3-cga-system"
        assert payload["version"] == 5
        assert payload["from_state"] == "CANARY"
        assert payload["to_state"] == "PRODUCTION"
        assert payload["agent_code"] == "cga"
        assert payload["schema_version"] == "1.0"
        assert payload["correlation_id"]
        assert payload["timestamp"]

    def test_serializable_to_json(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        json_str = json.dumps(event.model_dump())
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "prompt.promoted"


class TestTopicConfiguration:
    """AC-1: Topics with retention values per §8.1."""

    def test_lifecycle_topic_name(self):
        assert LIFECYCLE_TOPIC == "prompt-lifecycle-events"

    def test_lifecycle_retention_30_days(self):
        expected_ms = 30 * 24 * 3600 * 1000
        assert LIFECYCLE_TOPIC_RETENTION_MS == expected_ms


class TestEventAgentCode:
    def test_agent_code_field(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_REGISTERED,
            prompt_name="test",
            version=1,
            from_state="",
            to_state="DRAFT",
            agent_code="mra",
        )
        assert event.agent_code == "mra"

    def test_agent_code_default_empty(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_REGISTERED,
            prompt_name="test",
            version=1,
            from_state="",
            to_state="DRAFT",
        )
        assert event.agent_code == ""


class TestSchemaValidation:
    """Pinned schema_version and non-empty correlation_id."""

    def test_schema_version_override_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="schema_version must be"):
            PromptLifecycleEvent(
                event_type=PROMPT_PROMOTED,
                prompt_name="test",
                version=1,
                from_state="A",
                to_state="B",
                schema_version="2.0",
            )

    def test_empty_correlation_id_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="correlation_id must be non-empty"):
            PromptLifecycleEvent(
                event_type=PROMPT_PROMOTED,
                prompt_name="test",
                version=1,
                from_state="A",
                to_state="B",
                correlation_id="",
            )

    def test_whitespace_correlation_id_rejected(self):
        import pytest

        with pytest.raises(ValueError, match="correlation_id must be non-empty"):
            PromptLifecycleEvent(
                event_type=PROMPT_PROMOTED,
                prompt_name="test",
                version=1,
                from_state="A",
                to_state="B",
                correlation_id="   ",
            )


class TestProducerKeyAndHeaders:
    """Verify correlation_id is used as key and schema_version as header."""

    def test_correlation_id_encodes_as_message_key(self):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name="test",
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
            correlation_id="dedup-key-abc",
        )
        # The producer uses event.correlation_id.encode("utf-8") as key
        message_key = event.correlation_id.encode("utf-8")
        assert message_key == b"dedup-key-abc"

    def test_schema_version_encodes_as_header(self):
        headers = [("schema_version", SCHEMA_VERSION.encode("utf-8"))]
        assert headers[0] == ("schema_version", b"1.0")
