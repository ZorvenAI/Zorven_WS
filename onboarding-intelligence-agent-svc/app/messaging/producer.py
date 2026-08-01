"""Kafka producer wrapper.

A-05 provides only what the health probe needs: connect, report liveness,
close. Event emission — the topic catalogue, payload schemas and the
``agent.events.<tenant_id>`` fan-out — belongs to A-03, which raises the Kafka
and observability baseline.

**Kafka is optional in this fleet.** No `deployment/gcp` script provisions a
broker and every deployed service sets `*_KAFKA_ENABLED=false`, so an empty
``OIA_KAFKA_BOOTSTRAP_SERVERS`` means "this environment has no Kafka" and is
not a failure. When a broker *is* configured, it becomes a hard health
dependency — a configured-but-unreachable broker is a real fault.
"""

from __future__ import annotations

import logging

from aiokafka import AIOKafkaProducer

from app.core.config import Settings

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Thin lifecycle wrapper around ``AIOKafkaProducer``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None
        self._started = False

    @property
    def configured(self) -> bool:
        return self._settings.kafka_enabled

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Connect, if this environment has a broker at all."""
        if not self.configured:
            logger.info("Kafka not configured — event emission disabled")
            return
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.KAFKA_BOOTSTRAP_SERVERS,
            request_timeout_ms=2000,
        )
        await self._producer.start()
        self._started = True
        logger.info(
            "Kafka producer connected to %s",
            self._settings.KAFKA_BOOTSTRAP_SERVERS,
        )

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        self._started = False

    async def is_live(self) -> bool:
        """Whether a configured broker is actually reachable.

        Returns ``True`` when Kafka is not configured — absence is not a
        fault in an environment that has no broker by design. Callers that
        need to distinguish "absent" from "live" read :attr:`configured`.
        """
        if not self.configured:
            return True
        if self._producer is None or not self._started:
            return False
        try:
            cluster = self._producer.client.cluster
            return bool(cluster.brokers())
        except Exception:
            return False
