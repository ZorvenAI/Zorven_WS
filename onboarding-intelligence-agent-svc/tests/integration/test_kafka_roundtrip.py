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
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer, TopicPartition

from app.core.config import Settings
from app.events.catalog import EventType
from app.events.emitter import EventEmitter
from app.messaging.consumer import CommandConsumer
from app.messaging.producer import KafkaProducer
from app.messaging.provision import provision, retention_of, verify
from app.messaging.topics import (
    ARCHIVE,
    COMMANDS,
    DLQ,
    FLEET_TOPICS,
    GOLDEN_CANDIDATES,
    candidate_key,
    events_topic,
)

pytestmark = [pytest.mark.integration]

BOOTSTRAP = os.environ.get("OIA_TEST_KAFKA", "localhost:39092")

#: One probe topic for the whole run. Retrying with a *fresh* name each time
#: would be self-defeating: every attempt would face a partition whose leader
#: has just started being elected, so the probe would never observe the state
#: it is waiting for. Reusing one topic lets it settle across attempts.
PROBE_TOPIC = f"oia-readiness-probe-{uuid.uuid4().hex[:8]}"

#: topic -> its partitions, resolved once per run (see partitions_for).
_PARTITION_CACHE: dict[str, list] = {}


async def broker_serving() -> bool:
    """True once the broker can actually serve, not merely accept a socket.

    Connecting proves far less than it looks. A broker seconds into its life
    accepts admin connections while partition leaders are still being elected,
    so a produce times out and a consumer is told a just-created topic has no
    partitions. That is the gap CI was falling into: it waits for
    ``rpk cluster info``, which answers early, and started the tests about six
    seconds into the broker's life.

    So probe the two things the tests actually need — a partition with an
    elected leader, and a produce to it that is acknowledged — and treat
    anything less as not ready.

    It deliberately does *not* require a consumer to see the topic in its
    metadata cache. On CI's runner that never happens for an unsubscribed
    consumer, and the tests do not need it to: they assign partitions
    explicitly rather than discovering them.
    """
    from aiokafka import AIOKafkaProducer
    from aiokafka.admin import AIOKafkaAdminClient, NewTopic

    admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    await admin.start()
    try:
        try:
            await admin.create_topics(
                [NewTopic(PROBE_TOPIC, num_partitions=1, replication_factor=1)]
            )
        except Exception:
            pass  # already created by an earlier attempt
    finally:
        await admin.close()

    if not await partitions_for(PROBE_TOPIC, timeout=10):
        return False

    producer = AIOKafkaProducer(bootstrap_servers=BOOTSTRAP)
    await producer.start()
    try:
        # A leaderless partition fails here rather than mid-test.
        await asyncio.wait_for(producer.send_and_wait(PROBE_TOPIC, b"{}"), timeout=10)
    finally:
        await producer.stop()
    return True


@pytest.fixture(scope="module")
async def broker() -> str:
    """Wait for a serving broker; skip only where one was never promised.

    Bounded rather than immediate: a broker CI has only just launched is not
    absent, just not up yet.

    The distinction that matters is *who said there would be one*. When
    ``OIA_TEST_KAFKA`` is set, as CI sets it, a broker was promised and its
    absence is a failure — skipping there would turn a broken broker into a
    green run that silently covers none of AC-1, which is worse than an honest
    red. With no such promise, as in production, skipping is right.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 120
    last = "never reached"
    while loop.time() < deadline:
        try:
            if await broker_serving():
                return BOOTSTRAP
            last = "probe produced/consumed nothing"
        except Exception as exc:  # not up yet — connection refused and friends
            last = f"{type(exc).__name__}: {exc}"
        await asyncio.sleep(2)

    message = f"no serving Kafka broker at {BOOTSTRAP} after 120s — last: {last}"
    if "OIA_TEST_KAFKA" in os.environ:
        pytest.fail(f"{message}. OIA_TEST_KAFKA is set, so one was expected.")
    pytest.skip(message)


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


async def stop(consumer: Any) -> None:
    """Stop a consumer, tolerating an aiokafka shutdown race.

    Takes anything with a ``stop()`` — both ``AIOKafkaConsumer`` and this
    service's ``CommandConsumer``, which wraps one.

    A consumer created without a ``group_id`` gets a ``NoGroupCoordinator``,
    whose ``close()`` cancels an internal task and then awaits it. That task
    catches ``CancelledError`` and returns cleanly — but only once it has run
    at least one step. Cancel it before the loop has ever scheduled it and
    there is no ``except`` in place yet, so the ``CancelledError`` escapes
    ``consumer.stop()`` and fails the calling test.

    It surfaces when nothing is awaited between ``start()`` and ``stop()``,
    which is exactly the early-return path below. Reproduced 30/30 against a
    real broker on aiokafka 0.12 and 0.13.

    A genuine cancellation of *this* task is re-raised: ``cancelling()`` is
    non-zero only when the cancel was aimed at us, so a test being torn down
    by a timeout still dies as it should.
    """
    task = asyncio.current_task()
    try:
        await consumer.stop()
    except asyncio.CancelledError:
        if task is not None and task.cancelling() > 0:
            raise


async def partitions_for(topic: str, timeout: float = 30.0) -> list:
    """Partitions of ``topic`` that have an elected leader.

    Asked through the admin client rather than the consumer, deliberately.
    ``AIOKafkaConsumer.partitions_for_topic`` reads a *local* cache, so a
    consumer that has not subscribed to anything returns ``None`` — meaning
    "never asked", not "no partitions". Forcing a fetch with ``topics()`` is
    not enough either: on CI's runner a fresh consumer never populated that
    cache at all, across 120 s of retries, while the admin client answered
    immediately — which is why the provisioning tests passed there while every
    test that sized its read window through a consumer failed.

    ``describe_topics`` also reports the leader, and that is the signal really
    wanted. A partition is listed as soon as the topic is created, but cannot
    be produced to or read from until a leader is elected, so waiting on the
    leader is what separates "the topic exists" from "the topic works".

    Empty means no partition became usable inside ``timeout``.

    Answers are cached for the run. A topic's partitions do not change once it
    has been provisioned, and the helpers below call this on every read, so
    without the cache each call would stand up and tear down its own admin
    client — enough overhead to stall the suite.
    """
    from aiokafka.admin import AIOKafkaAdminClient

    if topic in _PARTITION_CACHE:
        return _PARTITION_CACHE[topic]

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    admin = AIOKafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    await admin.start()
    try:
        while True:
            try:
                described = await admin.describe_topics([topic])
            except Exception:
                described = []  # controller not answering yet
            for entry in described:
                if entry.get("topic") != topic or entry.get("error_code"):
                    continue
                ready = sorted(
                    part["partition"]
                    for part in entry.get("partitions", [])
                    if not part.get("error_code") and part.get("leader", -1) >= 0
                )
                if ready:
                    found = [TopicPartition(topic, p) for p in ready]
                    _PARTITION_CACHE[topic] = found
                    return found
            if loop.time() >= deadline:
                return []  # not cached: it may yet appear on a later call
            await asyncio.sleep(0.5)
    finally:
        await admin.close()


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
        assignment = await partitions_for(topic)
        if not assignment:
            return None
        consumer.assign(assignment)
        await consumer.seek_to_beginning(*assignment)
        message = await asyncio.wait_for(consumer.getone(), timeout=timeout)
        return json.loads(message.value)
    except asyncio.TimeoutError:
        return None
    finally:
        await stop(consumer)


async def end_offsets(topic: str) -> dict:
    """Where the topic ends *now*, so a test can read only what it adds.

    Scanning from the beginning does not scale: these topics retain messages
    for 1-30 days, so after a few runs the message under test sits behind a
    growing backlog and a bounded scan stops finding it. Reading forward from
    a captured offset is O(1) in history.
    """
    consumer = AIOKafkaConsumer(bootstrap_servers=BOOTSTRAP)
    await consumer.start()
    try:
        assignment = await partitions_for(topic)
        # Empty used to return {}, which made read_since return None without
        # reading anything — the test then failed on a missing message rather
        # than on the real cause. The topic is provisioned before this runs,
        # so no partitions means provisioning did not take.
        assert assignment, f"{topic} reports no partitions after provisioning"
        consumer.assign(assignment)
        return await consumer.end_offsets(assignment)
    finally:
        await stop(consumer)


async def read_since(
    topic: str, offsets: dict, predicate, timeout: float = 30.0
) -> dict | None:
    """Return the first message after ``offsets`` satisfying ``predicate``."""
    if not offsets:
        return None
    consumer = AIOKafkaConsumer(bootstrap_servers=BOOTSTRAP, enable_auto_commit=False)
    await consumer.start()
    try:
        consumer.assign(list(offsets))
        for partition, offset in offsets.items():
            consumer.seek(partition, offset)

        # get_running_loop() rather than get_event_loop(): the latter is
        # deprecated inside a coroutine on 3.12+ and warns or errors depending
        # on the runtime.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            try:
                message = await asyncio.wait_for(consumer.getone(), timeout=5)
            except asyncio.TimeoutError:
                continue
            body = json.loads(message.value)
            if predicate(body):
                return body
        return None
    finally:
        await stop(consumer)


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

        offsets = await end_offsets(spec.name)
        sent = await producer.send(
            spec.name, key="tenant:session", value=json.dumps(payload).encode()
        )
        assert sent, f"publish to {spec.name} reported no broker"

        received = await read_since(
            spec.name, offsets, lambda b: b.get("id") == probe_id
        )
        assert received is not None, f"no message returned from {spec.name}"
        assert received["probe"] == spec.name


async def test_event_reaches_the_per_tenant_events_topic(producer, broker):
    """The emitter's own path, end to end, on a real broker."""
    emitter = EventEmitter(producer)
    await emitter.start()
    tenant = uuid.uuid4()
    try:
        # A fresh tenant means a fresh topic, but capture offsets anyway so
        # the read is uniform with the others.
        await provision(broker)
        event = await emitter.emit(
            EventType.COVERAGE_UPDATED,
            tenant_id=tenant,
            correlation_id="corr-int-1",
            payload={"map": {"WF1": 0.71}},
        )
        assert await emitter.flush(timeout=20)

        received = await read_since(
            events_topic(str(tenant)),
            await end_offsets(events_topic(str(tenant))) or {},
            lambda b: b.get("event_id") == str(event.event_id),
        ) or await read_one(events_topic(str(tenant)))
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
    idempotency_key = f"idem-{uuid.uuid4().hex[:8]}"
    command = {
        "job_id": "job-1",
        "session_id": str(uuid.uuid4()),
        "evidence_manifest": {"manifest_hash": "abc123"},
        "idempotency_key": idempotency_key,
    }

    offsets = await end_offsets(DLQ.name)
    handled = await consumer.handle_raw(json.dumps(command).encode(), key="t:s")
    assert handled is False
    assert consumer.dead_lettered == 1

    letter = await read_since(
        DLQ.name, offsets, lambda b: b.get("idempotency_key") == idempotency_key
    )
    assert letter is not None, "no dead letter for this command reached the DLQ"
    assert letter["original_topic"] == COMMANDS.name
    assert letter["attempts"] == 2
    assert letter["error_code"] == "ERR-CMD-01"
    # §20: replay re-publishes with the same key, so it must survive.
    assert letter["idempotency_key"] == idempotency_key


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


async def test_auto_commit_is_disabled_on_the_real_consumer(settings, producer, broker):
    """Review finding: auto-commit can advance past an unhandled message.

    Renamed by the weak-assertion sweep. It was
    ``test_consumer_commits_only_after_handling``, which is not what it
    checks — it asserts the *precondition* for that behaviour (auto-commit
    off) on the real client, not that the commit follows handle_raw. Proving
    the ordering needs a consumer crashed mid-handle and a replay observed,
    which is N-03's failure-injection story.

    A name that overstates its test is worse than a narrow test: it makes the
    gap invisible to anyone auditing coverage.
    """
    from app.messaging.consumer import CommandConsumer

    consumer = CommandConsumer(settings, producer)
    await consumer.start()
    try:
        assert consumer._consumer is not None
        # The contract, asserted on the real client the service will use.
        assert consumer._consumer._enable_auto_commit is False
    finally:
        await stop(consumer)


# ── L-02 · golden-dataset topic ────────────────────────────────────


async def test_golden_candidate_topic_provisioned(broker):
    """AC-1: the golden-dataset topic is created by provision()."""
    report = await provision(broker)
    assert GOLDEN_CANDIDATES.name in report.all_present


async def test_golden_candidate_topic_retention(broker):
    """AC-1: 30-day retention per §13.1."""
    await provision(broker)
    actual = await retention_of(broker, GOLDEN_CANDIDATES.name)
    assert actual == str(GOLDEN_CANDIDATES.retention_ms)


async def test_golden_candidate_key_shape(producer, broker):
    """AC-1: key is {tenant_id}:{prompt_id}."""
    await provision(broker)
    tenant = str(uuid.uuid4())
    prompt_id = "oia.extract_fields"
    key = candidate_key(tenant, prompt_id)
    assert key == f"{tenant}:{prompt_id}"

    payload = {"probe": "golden-candidate", "id": str(uuid.uuid4())}
    offsets = await end_offsets(GOLDEN_CANDIDATES.name)
    sent = await producer.send(
        GOLDEN_CANDIDATES.name, key=key, value=json.dumps(payload).encode()
    )
    assert sent

    received = await read_since(
        GOLDEN_CANDIDATES.name, offsets, lambda b: b.get("id") == payload["id"]
    )
    assert received is not None
    assert received["probe"] == "golden-candidate"


async def test_golden_candidate_roundtrip(producer, broker):
    """Full path: publish envelope → consume → verify shape."""
    from app.messaging.schemas import GoldenCandidate, MessageEnvelope

    await provision(broker)
    tenant = uuid.uuid4()
    session = uuid.uuid4()

    candidate = GoldenCandidate(
        prompt_id="oia.extract_fields",
        prompt_version="v3.1",
        field_name="company_name",
        input_evidence_ref="recording:r1:10.0-15.0",
        extracted_value="[REDACTED]",
        admin_final_value="Acme Corp",
        edit_distance=0.34,
        classification="KEY",
        accepted_without_edit=False,
    )
    envelope = MessageEnvelope(
        correlation_id=uuid.uuid4().hex,
        tenant_id=tenant,
        session_id=session,
        payload=candidate.model_dump(mode="json"),
    )

    offsets = await end_offsets(GOLDEN_CANDIDATES.name)
    key = candidate_key(str(tenant), "oia.extract_fields")
    sent = await producer.send(
        GOLDEN_CANDIDATES.name,
        key=key,
        value=json.dumps(envelope.model_dump(mode="json")).encode(),
    )
    assert sent

    received = await read_since(
        GOLDEN_CANDIDATES.name,
        offsets,
        lambda b: b.get("correlation_id") == envelope.correlation_id,
    )
    assert received is not None
    assert received["tenant_id"] == str(tenant)
    assert received["session_id"] == str(session)
    assert received["payload"]["prompt_id"] == "oia.extract_fields"
    assert received["payload"]["prompt_version"] == "v3.1"
    assert received["payload"]["edit_distance"] == 0.34


# ── N-03 AC-3: DLQ replay tool ──────────────────────────────────────


async def test_archive_topic_provisioned(broker):
    """AC-3: the archive topic is created by provision()."""
    report = await provision(broker)
    assert ARCHIVE.name in report.all_present


async def test_archive_topic_retention(broker):
    """AC-3: 90-day retention for poison messages."""
    await provision(broker)
    actual = await retention_of(broker, ARCHIVE.name)
    assert actual == str(ARCHIVE.retention_ms)


async def test_replay_preserves_idempotency_key(settings, producer, broker):
    """AC-3: replayed messages keep the same idempotency_key."""
    from app.messaging.dlq_replay import replay_batch

    await provision(broker)

    idempotency_key = f"idem-replay-{uuid.uuid4().hex[:8]}"
    dead_letter = {
        "original_topic": COMMANDS.name,
        "original_key": "t:s",
        "payload": {
            "job_id": "job-replay-1",
            "session_id": str(uuid.uuid4()),
            "evidence_manifest": {"manifest_hash": "abc"},
        },
        "error_code": "ERR-CMD-01",
        "error_message": "handler exploded",
        "attempts": 1,
        "failed_at": "2026-09-04T00:00:00Z",
        "idempotency_key": idempotency_key,
    }

    await producer.send(DLQ.name, key="t:s", value=json.dumps(dead_letter).encode())

    offsets_cmd = await end_offsets(COMMANDS.name)

    summary = await replay_batch(
        producer,
        bootstrap_servers=broker,
        batch_size=10,
    )

    assert summary.replayed >= 1
    assert summary.archived == 0

    received = await read_since(
        COMMANDS.name,
        offsets_cmd,
        lambda b: b.get("idempotency_key") == idempotency_key,
    )
    assert received is not None, "replayed message not found on commands topic"
    assert received["idempotency_key"] == idempotency_key
    assert received["job_id"] == "job-replay-1"


async def test_poison_message_archived_after_three_attempts(settings, producer, broker):
    """AC-3: messages with attempts >= 3 go to the archive, not back to commands."""
    from app.messaging.dlq_replay import replay_batch

    await provision(broker)

    idempotency_key = f"idem-poison-{uuid.uuid4().hex[:8]}"
    poison = {
        "original_topic": COMMANDS.name,
        "original_key": "t:s",
        "payload": {
            "job_id": "job-poison-1",
            "session_id": str(uuid.uuid4()),
            "evidence_manifest": {"manifest_hash": "xyz"},
        },
        "error_code": "ERR-CMD-01",
        "error_message": "permanently broken",
        "attempts": 3,
        "failed_at": "2026-09-04T00:00:00Z",
        "idempotency_key": idempotency_key,
    }

    await producer.send(DLQ.name, key="t:s", value=json.dumps(poison).encode())

    offsets_archive = await end_offsets(ARCHIVE.name)
    offsets_cmd = await end_offsets(COMMANDS.name)

    summary = await replay_batch(
        producer,
        bootstrap_servers=broker,
        batch_size=10,
    )

    assert summary.archived >= 1
    assert summary.replayed == 0

    archived = await read_since(
        ARCHIVE.name,
        offsets_archive,
        lambda b: b.get("idempotency_key") == idempotency_key,
    )
    assert archived is not None, "poison message not found on archive topic"

    replayed = await read_since(
        COMMANDS.name,
        offsets_cmd,
        lambda b: b.get("idempotency_key") == idempotency_key,
        timeout=5,
    )
    assert replayed is None, "poison message should NOT appear on commands topic"


async def test_dlq_replay_no_duplicate_writes(settings, producer, broker):
    """AC-3: replaying twice with the same idempotency_key does not duplicate."""
    from app.messaging.dlq_replay import replay_batch

    await provision(broker)

    idempotency_key = f"idem-nodup-{uuid.uuid4().hex[:8]}"
    dead_letter = {
        "original_topic": COMMANDS.name,
        "original_key": "t:s",
        "payload": {
            "job_id": "job-nodup-1",
            "session_id": str(uuid.uuid4()),
            "evidence_manifest": {"manifest_hash": "abc"},
        },
        "error_code": "ERR-CMD-01",
        "error_message": "handler exploded",
        "attempts": 1,
        "failed_at": "2026-09-04T00:00:00Z",
        "idempotency_key": idempotency_key,
    }

    await producer.send(DLQ.name, key="t:s", value=json.dumps(dead_letter).encode())

    offsets_cmd = await end_offsets(COMMANDS.name)

    s1 = await replay_batch(producer, bootstrap_servers=broker, batch_size=10)
    s2 = await replay_batch(producer, bootstrap_servers=broker, batch_size=10)

    assert s1.replayed >= 1
    assert s2.replayed == 0, "second replay should find nothing — consumer committed"

    seen: list[dict] = []
    consumer = AIOKafkaConsumer(bootstrap_servers=broker, enable_auto_commit=False)
    await consumer.start()
    try:
        assignment = await partitions_for(COMMANDS.name)
        consumer.assign(assignment)
        for tp, offset in offsets_cmd.items():
            consumer.seek(tp, offset)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10
        while loop.time() < deadline:
            try:
                msg = await asyncio.wait_for(consumer.getone(), timeout=3)
                body = json.loads(msg.value)
                if body.get("idempotency_key") == idempotency_key:
                    seen.append(body)
            except asyncio.TimeoutError:
                break
    finally:
        await stop(consumer)

    assert len(seen) == 1, f"expected exactly 1 replayed message, got {len(seen)}"
