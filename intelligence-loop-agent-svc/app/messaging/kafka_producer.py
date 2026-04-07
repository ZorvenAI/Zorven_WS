"""Kafka producers for ILA (audit + events). Fail-open if no brokers."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from aiokafka import AIOKafkaProducer
except ImportError:  # pragma: no cover
    AIOKafkaProducer = None  # type: ignore


class _Producer:
    def __init__(self, bootstrap: str, topic: str):
        self._bootstrap = bootstrap
        self._topic = topic
        self._producer: Any = None

    async def start(self):
        if not self._bootstrap or AIOKafkaProducer is None:
            logger.info("Kafka disabled for topic=%s (fail-open)", self._topic)
            return
        try:
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v, default=str).encode(),
            )
            await self._producer.start()
            logger.info("Kafka producer started topic=%s", self._topic)
        except Exception as exc:
            logger.warning("Kafka start failed (fail-open): %s", exc)
            self._producer = None

    async def stop(self):
        if self._producer:
            try:
                await self._producer.stop()
            except Exception:
                pass

    async def send(self, payload: dict):
        if not self._producer:
            return
        try:
            await self._producer.send_and_wait(self._topic, payload)
        except Exception as exc:
            logger.warning("Kafka send failed (fail-open): %s", exc)


class AuditProducer(_Producer):
    pass


class EventProducer(_Producer):
    pass
