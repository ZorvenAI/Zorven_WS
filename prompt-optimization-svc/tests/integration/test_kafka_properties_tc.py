"""Hypothesis property tests for Kafka via testcontainers (US-059).

Property-based tests that verify Kafka message invariants hold for
arbitrary inputs against a real Kafka container.
"""

import json
import os

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from app.kafka.producer import LifecycleProducer
from app.kafka.schemas import PROMPT_PROMOTED


@pytest.mark.integration
@pytest.mark.property
class TestKafkaPropertiesTC:
    """Hypothesis property tests against real Kafka."""

    @pytest.fixture
    async def lifecycle_producer(self):
        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        producer = LifecycleProducer(bootstrap)
        await producer.start()
        yield producer
        await producer.stop()

    @pytest.fixture
    async def lifecycle_consumer(self):
        from aiokafka import AIOKafkaConsumer

        bootstrap = os.environ.get("POI_KAFKA_BOOTSTRAP_SERVERS", "")
        consumer = AIOKafkaConsumer(
            LifecycleProducer.TOPIC,
            bootstrap_servers=bootstrap,
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            consumer_timeout_ms=10000,
            group_id="tc-prop-lifecycle",
        )
        await consumer.start()
        yield consumer
        await consumer.stop()

    @given(
        prompt_name=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="-_",
            ),
            min_size=1,
            max_size=50,
        ),
        version=st.integers(min_value=1, max_value=9999),
    )
    @h_settings(
        max_examples=5,
        deadline=30000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_lifecycle_event_roundtrips_through_kafka(
        self, lifecycle_producer, lifecycle_consumer, prompt_name, version
    ):
        """Random event fields serialize/deserialize correctly through Kafka."""
        tagged_name = f"__tc_prop_{prompt_name}"
        lifecycle_producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name=tagged_name,
            version=version,
            from_state="DRAFT",
            to_state="PRODUCTION",
            correlation_id=f"prop-rt-{version}",
        )

        async for msg in lifecycle_consumer:
            if msg.value.get("prompt_name") == tagged_name:
                assert msg.value["version"] == version
                assert msg.value["event_type"] == PROMPT_PROMOTED
                break

    @given(
        correlation_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="-_",
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @h_settings(
        max_examples=5,
        deadline=30000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_correlation_id_preserved_as_key(
        self, lifecycle_producer, lifecycle_consumer, correlation_id
    ):
        """Random correlation IDs appear as Kafka message key."""
        tagged_name = f"__tc_prop_key_{correlation_id[:20]}"
        lifecycle_producer.send_lifecycle_event_sync(
            event_type=PROMPT_PROMOTED,
            prompt_name=tagged_name,
            version=1,
            from_state="DRAFT",
            to_state="CANARY",
            correlation_id=correlation_id,
        )

        async for msg in lifecycle_consumer:
            if msg.value.get("prompt_name") == tagged_name:
                assert msg.key is not None
                assert msg.key.decode("utf-8") == correlation_id
                break
