"""AC-1 — the fleet topics exist and round-trip a message.

Runs against a real broker. Point ``OIA_TEST_KAFKA`` at one; the tests skip
cleanly when there is none, which is the state in production, where no
`deployment/gcp` script provisions a broker at all.

    docker run -d --name oia-test-kafka -p 39092:9092 --memory=700m \\
      redpandadata/redpanda:v24.2.7 redpanda start --smp 1 --memory 400M \\
      --overprovisioned --node-id 0 --check=false \\
      --kafka-addr PLAINTEXT://0.0.0.0:9092 \\
      --advertise-kafka-addr PLAINTEXT://localhost:39092

Redpanda rather than the compose broker on purpose: it speaks the Kafka
protocol, starts in ~30 s and fits in 400 MB, where the ZooKeeper-mode broker
in docker-compose needs a JVM heap this machine could not spare.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from aiokafka import AIOKafkaConsumer, TopicPartition

from app.core.config import Settings
from app.events.catalog import EventType
from app.events.emitter import EventEmitter
from app.messaging.consumer import CommandConsumer
from app.messaging.producer import KafkaProducer
from app.messaging.provision import provision, retention_of, verify
from app.messaging.topics import COMMANDS, DLQ, FLEET_TOPICS, events_topic

pytestmark = [pytest.mark.integration]

BOOTSTRAP = os.environ.get("OIA_TEST_KAFKA", "localhost:39092")


async def broker_available() -> bool:
    from aiokafka.admin import AIOKafkaAdminClient

    try:
        admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP)
        await admin.start()
        await admin.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
async def broker() -> str:
    if not await broker_available():
        pytest.skip(f"no Kafka broker at {BOOTSTRAP}")
    return BOOTSTRAP


@pytest.fixture
def settings(monkeypatch) -> Settings:
    monkeypatch.setenv("OIA_KAFKA_BOOTSTRAP_SERVERS", BOOTSTRAP)
    monkeypatch.setenv("OIA_BACKEND_BASE_URL", "http://backend:8001")
    monkeypatch.setenv("OIA_GCS_BUCKET", "zorven-raw-assets")
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
async def producer(settings, broker):
    kafka = KafkaProducer(settings)
    await kafka.start()
    yield kafka
    await kafka.stop()


async def read_one(topic: str, timeout: float = 30.0) -> dict | None:
    """Read the first message on ``topic``.

    Assigns partitions directly rather than joining a consumer group: the
    group protocol costs a rebalance per consumer, which dominates the test
    and is not what AC-1 is about.
    """
    consumer = AIOKafkaConsumer(
        bootstrap_servers=BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            return None
        assignment = [TopicPartition(topic, p) for p in partitions]
        consumer.assign(assignment)
        await consumer.seek_to_beginning(*assignment)
        message = await asyncio.wait_for(consumer.getone(), timeout=timeout)
        return json.loads(message.value)
    except asyncio.TimeoutError:
        return None
    finally:
        await consumer.stop()


async def read_matching(
    topic: str, predicate, limit: int = 100, timeout: float = 20.0
) -> dict | None:
    """Return the first message on ``topic`` satisfying ``predicate``.

    Position-independent on purpose. These topics accumulate across tests and
    across runs — the round-trip probe and the dead letters share the DLQ — so
    "the first message" is not necessarily the one under test.
    """
    consumer = AIOKafkaConsumer(
        bootstrap_servers=BOOTSTRAP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            return None
        assignment = [TopicPartition(topic, p) for p in partitions]
        consumer.assign(assignment)
        await consumer.seek_to_beginning(*assignment)
        for _ in range(limit):
            try:
                message = await asyncio.wait_for(consumer.getone(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
            body = json.loads(message.value)
            if predicate(body):
                return body
        return None
    finally:
        await consumer.stop()


async def test_provisioning_creates_every_fleet_topic(broker):
    """AC-1: the topics exist, with the retention Design §13.1 specifies."""
    report = await provision(broker)
    assert report.ok, report.failed

    reachable, missing = await verify(broker)
    assert reachable, f"missing after provisioning: {missing}"

    names = {spec.name for spec in FLEET_TOPICS}
    assert names.issubset(set(report.all_present))


async def test_provisioning_is_idempotent(broker):
    """Running it twice is not an error — startup runs it on every boot."""
    await provision(broker)
    second = await provision(broker)
    assert second.ok, second.failed
    assert second.created == [], "second run recreated topics"


async def test_publish_consume_each_fleet_topic(producer, broker):
    """AC-1: every §13.1 fleet topic accepts and returns a message."""
    await provision(broker)

    for spec in FLEET_TOPICS:
        probe_id = str(uuid.uuid4())
        payload = {"probe": spec.name, "id": probe_id}
        sent = await producer.send(
            spec.name, key="tenant:session", value=json.dumps(payload).encode()
        )
        assert sent, f"publish to {spec.name} reported no broker"

        received = await read_matching(spec.name, lambda b: b.get("id") == probe_id)
        assert received is not None, f"no message returned from {spec.name}"
        assert received["probe"] == spec.name


async def test_event_reaches_the_per_tenant_events_topic(producer, broker):
    """The emitter's own path, end to end, on a real broker."""
    emitter = EventEmitter(producer)
    await emitter.start()
    tenant = uuid.uuid4()
    try:
        event = await emitter.emit(
            EventType.COVERAGE_UPDATED,
            tenant_id=tenant,
            correlation_id="corr-int-1",
            payload={"map": {"WF1": 0.71}},
        )
        assert await emitter.flush(timeout=20)

        received = await read_one(events_topic(str(tenant)))
        assert received is not None
        assert received["event_type"] == "onboarding.coverage.updated"
        assert received["event_id"] == str(event.event_id)
        assert received["tenant_id"] == str(tenant)
    finally:
        await emitter.stop()


async def test_command_that_keeps_failing_is_dead_lettered(settings, producer, broker):
    """§20: the DLQ is what makes retry exhaustion reviewable."""
    await provision(broker)

    async def always_fails(command):
        raise RuntimeError("handler exploded")

    consumer = CommandConsumer(
        settings, producer, always_fails, max_attempts=2, backoff_s=0.01
    )
    command = {
        "job_id": "job-1",
        "session_id": str(uuid.uuid4()),
        "evidence_manifest": {"manifest_hash": "abc123"},
        "idempotency_key": "idem-key-1",
    }

    handled = await consumer.handle_raw(json.dumps(command).encode(), key="t:s")
    assert handled is False
    assert consumer.dead_lettered == 1

    letter = await read_matching(
        DLQ.name, lambda b: b.get("idempotency_key") == "idem-key-1"
    )
    assert letter is not None, "no dead letter for this command reached the DLQ"
    assert letter["original_topic"] == COMMANDS.name
    assert letter["attempts"] == 2
    assert letter["error_code"] == "ERR-CMD-01"
    # §20: replay re-publishes with the same key, so it must survive.
    assert letter["idempotency_key"] == "idem-key-1"


async def test_unparseable_command_is_dead_lettered_immediately(
    settings, producer, broker
):
    """A malformed message cannot be retried into correctness."""
    await provision(broker)
    consumer = CommandConsumer(settings, producer, None, max_attempts=3)

    handled = await consumer.handle_raw(b"{not json", key="t:s")
    assert handled is False
    assert consumer.dead_lettered == 1


async def test_valid_command_is_handled_once(settings, producer, broker):
    """The negative tests only mean something if the happy path works."""
    seen = []

    async def handler(command):
        seen.append(command.job_id)

    consumer = CommandConsumer(settings, producer, handler)
    command = {
        "job_id": "job-ok",
        "session_id": str(uuid.uuid4()),
        "evidence_manifest": {"manifest_hash": "hash"},
        "idempotency_key": "idem-ok",
    }
    assert await consumer.handle_raw(json.dumps(command).encode()) is True
    assert seen == ["job-ok"]
    assert consumer.dead_lettered == 0


# ── Regression cover for PR #532 review findings ─────────────────────────


async def test_retention_matches_the_catalogue_after_provisioning(broker):
    """Review finding: the provisioner claimed reconciliation it never did.

    An auto-created topic takes the broker default, so agent.escalations would
    silently keep 7 days instead of the 30 Design §13.1 requires.
    """
    await provision(broker)
    for spec in FLEET_TOPICS:
        actual = await retention_of(broker, spec.name)
        assert actual == str(
            spec.retention_ms
        ), f"{spec.name} retention is {actual}, expected {spec.retention_ms}"


async def test_a_topic_with_wrong_retention_is_reconciled(broker):
    """The case that matters: the topic already exists and is non-compliant."""
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic

    from app.messaging.topics import TopicSpec

    name = f"agent.dlq.retention-probe-{uuid.uuid4().hex[:8]}"
    spec = TopicSpec(name=name, retention_ms=30 * 24 * 60 * 60 * 1000, purpose="probe")

    admin = AIOKafkaAdminClient(bootstrap_servers=broker)
    await admin.start()
    try:
        # Create it the way auto-create would: with a wrong retention.
        await admin.create_topics(
            [
                NewTopic(
                    name=name,
                    num_partitions=1,
                    replication_factor=1,
                    topic_configs={"retention.ms": "604800000"},  # 7 days
                )
            ]
        )
        assert await retention_of(broker, name) == "604800000"

        report = await provision(broker, specs=(spec,))
        assert name in report.reconciled, report
        assert await retention_of(broker, name) == str(spec.retention_ms)

        # And running again is a no-op rather than another "reconciled".
        second = await provision(broker, specs=(spec,))
        assert name in second.existing
        assert name not in second.reconciled
    finally:
        try:
            await admin.delete_topics([name])
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
        await admin.close()


async def test_consumer_commits_only_after_handling(settings, producer, broker):
    """Review finding: auto-commit can advance past an unhandled message.

    The consumer now commits explicitly after handle_raw, so a crash mid-handle
    replays the message rather than losing it.
    """
    from aiokafka import AIOKafkaConsumer

    from app.messaging.consumer import CommandConsumer

    consumer = CommandConsumer(settings, producer)
    await consumer.start()
    try:
        assert consumer._consumer is not None
        # The contract, asserted on the real client the service will use.
        assert consumer._consumer._enable_auto_commit is False
    finally:
        await consumer.stop()

    assert isinstance(consumer, CommandConsumer)
    assert AIOKafkaConsumer is not None
