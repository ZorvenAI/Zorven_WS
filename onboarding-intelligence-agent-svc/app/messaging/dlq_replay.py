"""DLQ replay tool — re-publish dead-lettered commands (Design §20, N-03).

Reads a batch from the DLQ topic, re-publishes each to its original topic
with the same idempotency_key (which is what makes replay safe by
construction), and archives poison messages after three replay attempts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from aiokafka import AIOKafkaConsumer

from app.messaging.producer import KafkaProducer
from app.messaging.schemas import DeadLetter
from app.messaging.topics import ARCHIVE, DLQ

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10
POISON_THRESHOLD = 3


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
                await consumer.commit()
    finally:
        await consumer.stop()

    return summary


async def _handle_one(
    producer: KafkaProducer,
    message: object,
    summary: ReplaySummary,
) -> None:
    raw = getattr(message, "value", b"")
    key_bytes = getattr(message, "key", None)
    key = key_bytes.decode() if key_bytes else None

    try:
        body = json.loads(raw)
        letter = DeadLetter.model_validate(body)
    except Exception as exc:
        logger.warning("dlq_replay_unparseable", error=str(exc))
        summary.errors += 1
        summary.details.append({"action": "error", "reason": str(exc)})
        return

    if letter.attempts >= POISON_THRESHOLD:
        await producer.send(
            ARCHIVE.name,
            key=key,
            value=raw,
        )
        logger.info(
            "dlq_message_archived",
            error_code=letter.error_code,
            attempts=letter.attempts,
        )
        summary.archived += 1
        summary.details.append(
            {
                "action": "archived",
                "error_code": letter.error_code,
                "attempts": str(letter.attempts),
            }
        )
        return

    replay_payload = letter.payload
    if letter.idempotency_key and isinstance(replay_payload, dict):
        replay_payload["idempotency_key"] = letter.idempotency_key

    await producer.send(
        letter.original_topic,
        key=key,
        value=json.dumps(replay_payload).encode(),
    )
    logger.info(
        "dlq_message_replayed",
        original_topic=letter.original_topic,
        idempotency_key=letter.idempotency_key,
    )
    summary.replayed += 1
    summary.details.append(
        {
            "action": "replayed",
            "topic": letter.original_topic,
            "idempotency_key": letter.idempotency_key or "",
        }
    )
