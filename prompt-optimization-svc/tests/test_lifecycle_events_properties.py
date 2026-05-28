"""Hypothesis property tests for lifecycle events (US-036)."""

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from app.kafka.schemas import (
    PROMPT_PROMOTED,
    PROMPT_REGISTERED,
    SCHEMA_VERSION,
    PromptLifecycleEvent,
)


class TestLifecycleEventProperties:
    @given(st.text(min_size=1, max_size=30), st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_correlation_id_always_present(self, name, version):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name=name,
            version=version,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        assert event.correlation_id
        assert len(event.correlation_id) > 0

    @given(st.text(min_size=1, max_size=30), st.integers(min_value=1, max_value=100))
    @settings(max_examples=50, deadline=None)
    def test_schema_version_always_1_0(self, name, version):
        event = PromptLifecycleEvent(
            event_type=PROMPT_REGISTERED,
            prompt_name=name,
            version=version,
            from_state="",
            to_state="DRAFT",
        )
        assert event.schema_version == SCHEMA_VERSION

    @given(st.text(min_size=1, max_size=30))
    @settings(max_examples=30, deadline=None)
    def test_always_serializable_to_json(self, name):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name=name,
            version=1,
            from_state="CANARY",
            to_state="PRODUCTION",
        )
        json_str = json.dumps(event.model_dump())
        parsed = json.loads(json_str)
        assert parsed["event_type"] == "prompt.promoted"

    @given(st.text(min_size=1, max_size=30))
    @settings(max_examples=30, deadline=None)
    def test_timestamp_always_present(self, name):
        event = PromptLifecycleEvent(
            event_type=PROMPT_PROMOTED,
            prompt_name=name,
            version=1,
            from_state="A",
            to_state="B",
        )
        assert event.timestamp
        assert "T" in event.timestamp  # ISO format
