"""agent.commands consumer with dead-letter routing (Design §13, §20).

A-03 delivers the transport: consume, validate, hand to a handler, retry with
backoff, and dead-letter on exhaustion. The PROCESS handler itself is J-01's.

Dead-lettering is the point. §20 says the DLQ is reviewed daily and the replay
tool re-publishes with the same ``idempotency_key``, "so replay is safe by
construction" — which only holds if the key survives into the dead letter, so
:class:`DeadLetter` carries it.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from aiokafka import AIOKafkaConsumer

from app.core.config import Settings
from app.core.logging import get_logger
from app.messaging.producer import KafkaProducer
from app.messaging.schemas import DeadLetter, ProcessCommand
from app.messaging.topics import COMMANDS, DLQ

logger = get_logger(__name__)

CommandHandler = Callable[[ProcessCommand], Awaitable[None]]

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_S = 0.5


class CommandConsumer:
    """Consumes ``agent.commands.onboarding-intelligence``."""

    def __init__(
        self,
        settings: Settings,
        producer: KafkaProducer,
        handler: CommandHandler | None = None,
        *,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_s: float = DEFAULT_BACKOFF_S,
    ) -> None:
        self._settings = settings
        self._producer = producer
        self._handler = handler
        self._max_attempts = max_attempts
        self._backoff_s = backoff_s
        self._consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task[None] | None = None
        self.dead_lettered = 0
        self.processed = 0

    @property
    def configured(self) -> bool:
        return self._settings.kafka_enabled

    async def start(self) -> None:
        if not self.configured:
            logger.info("kafka_not_configured", detail="command consumer disabled")
            return
        self._consumer = AIOKafkaConsumer(
            COMMANDS.name,
            bootstrap_servers=self._settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=f"{COMMANDS.name}.consumers",
            # Offsets are committed explicitly, after handle_raw has either
            # succeeded or dead-lettered. On a timer, auto-commit can advance
            # past a message this process never finished handling, and the
            # message is simply lost on restart — retries and the DLQ only
            # help if the offset has not already moved.
            enable_auto_commit=False,
            auto_offset_reset="latest",
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self._run())
        logger.info("command_consumer_started", topic=COMMANDS.name)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def _run(self) -> None:
        assert self._consumer is not None
        async for message in self._consumer:
            await self.handle_raw(
                message.value,
                key=message.key.decode() if message.key else None,
            )
            # Committed regardless of outcome: a failure has already been
            # retried and dead-lettered inside handle_raw, so replaying it
            # would duplicate the dead letter rather than recover anything.
            await self._consumer.commit()

    async def handle_raw(self, raw: bytes, *, key: str | None = None) -> bool:
        """Process one message. Returns True when it was handled.

        Kept separate from the consume loop so the retry and dead-letter
        behaviour can be tested against a real broker without waiting on a
        subscription.
        """
        try:
            body: dict[str, Any] = json.loads(raw)
            command = ProcessCommand.model_validate(body)
        except Exception as exc:  # noqa: BLE001 — malformed input is a dead letter
            await self._dead_letter(
                raw, key, "ERR-MSG-01", f"unparseable command: {exc}", attempts=1
            )
            return False

        for attempt in range(1, self._max_attempts + 1):
            try:
                if self._handler is not None:
                    await self._handler(command)
                self.processed += 1
                return True
            except Exception as exc:  # noqa: BLE001 — retried, then dead-lettered
                logger.warning(
                    "command_handler_failed",
                    attempt=attempt,
                    job_id=command.job_id,
                    error=str(exc),
                )
                if attempt >= self._max_attempts:
                    await self._dead_letter(
                        raw,
                        key,
                        "ERR-CMD-01",
                        str(exc),
                        attempts=attempt,
                        idempotency_key=command.idempotency_key,
                    )
                    return False
                await asyncio.sleep(self._backoff_s * attempt)
        return False

    async def _dead_letter(
        self,
        raw: bytes,
        key: str | None,
        error_code: str,
        error_message: str,
        *,
        attempts: int,
        idempotency_key: str | None = None,
    ) -> None:
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001 — keep what we can for triage
            payload = {"unparseable": raw[:512].decode(errors="replace")}

        letter = DeadLetter(
            original_topic=COMMANDS.name,
            original_key=key,
            payload=payload,
            error_code=error_code,
            error_message=error_message[:500],
            attempts=attempts,
            idempotency_key=idempotency_key,
        )
        self.dead_lettered += 1

        from app.metrics import DLQ_DEPTH

        DLQ_DEPTH.set(self.dead_lettered)
        logger.error(
            "command_dead_lettered",
            error_code=error_code,
            attempts=attempts,
            dlq_topic=DLQ.name,
        )
        await self._producer.send(
            DLQ.name,
            key=key,
            value=json.dumps(letter.model_dump(mode="json")).encode(),
        )
