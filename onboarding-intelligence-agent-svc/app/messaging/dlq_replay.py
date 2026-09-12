"""DLQ replay tool — re-publish dead-lettered commands (Design §20, N-03).

Reads a batch from the DLQ topic, re-publishes each to its original topic
with the same idempotency_key (which is what makes replay safe by
construction), and archives poison messages after exhausting replay
attempts.

The threshold is based on ``_replay_attempts`` (carried in the command
payload through re-dead-lettering), NOT on the original handler
``attempts`` — CommandConsumer writes ``attempts=max_attempts`` when
dead-lettering, so using that field would archive every message on
first replay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from aiokafka import AIOKafkaConsumer, TopicPartition

from app.core.logging import get_logger
from app.messaging.producer import KafkaProducer
from app.messaging.schemas import DeadLetter
from app.messaging.topics import ARCHIVE, DLQ

logger = get_logger(__name__)

DEFAULT_BATCH_SIZE = 10
POISON_REPLAY_THRESHOLD = 3


@dataclass
class ReplaySummary:
    replayed: int = 0
    archived: int = 0
    errors: int = 0
    details: list[dict[str, str]] = field(default_factory=list)


async def replay_batch(
    producer: KafkaProducer,
    *,
    bootstrap_servers: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    poll_timeout_ms: int = 5000,
) -> ReplaySummary:
    """Read up to *batch_size* DLQ messages and replay or archive each."""
    summary = ReplaySummary()

    consumer = AIOKafkaConsumer(
        DLQ.name,
        bootstrap_servers=bootstrap_servers,
        group_id="dlq-replay",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        records = await consumer.getmany(
            timeout_ms=poll_timeout_ms, max_records=batch_size
        )
        for _tp, messages in records.items():
            for message in messages:
                await _handle_one(producer, message, summary)
                tp = TopicPartition(message.topic, message.partition)
                await consumer.commit({tp: message.offset + 1})
    finally:
        await consumer.stop()

    return summary


async def _handle_one(
    producer: KafkaProducer,
    message: object,
    summary: ReplaySummary,
) -> None:
    raw = getattr(message, "value", b"")

    try:
        body = json.loads(raw)
        letter = DeadLetter.model_validate(body)
    except Exception as exc:
        logger.warning("dlq_replay_unparseable", error=str(exc))
        summary.errors += 1
        summary.details.append({"action": "error", "reason": str(exc)})
        return

    replay_attempts = 0
    if isinstance(letter.payload, dict):
        replay_attempts = letter.payload.get("_replay_attempts", 0)

    if replay_attempts >= POISON_REPLAY_THRESHOLD:
        await producer.send(
            ARCHIVE.name,
            key=letter.original_key,
            value=raw,
        )
        logger.info(
            "dlq_message_archived",
            error_code=letter.error_code,
            replay_attempts=replay_attempts,
        )
        summary.archived += 1
        summary.details.append(
            {
                "action": "archived",
                "error_code": letter.error_code,
                "replay_attempts": str(replay_attempts),
            }
        )
        return

    replay_payload = (
        letter.payload.copy() if isinstance(letter.payload, dict) else letter.payload
    )
    if isinstance(replay_payload, dict):
        if letter.idempotency_key:
            replay_payload["idempotency_key"] = letter.idempotency_key
        replay_payload["_replay_attempts"] = replay_attempts + 1

    await producer.send(
        letter.original_topic,
        key=letter.original_key,
        value=json.dumps(replay_payload).encode(),
    )
    logger.info(
        "dlq_message_replayed",
        original_topic=letter.original_topic,
        idempotency_key=letter.idempotency_key,
        replay_attempt=replay_attempts + 1,
    )
    summary.replayed += 1
    summary.details.append(
        {
            "action": "replayed",
            "topic": letter.original_topic,
            "idempotency_key": letter.idempotency_key or "",
        }
    )
