"""
Kafka Adapter.

Concrete implementation of KafkaPort for publishing messages
to Kafka topics.
"""

import json
import logging
from typing import Any, Optional

from django.conf import settings

from rag_index.domain.exceptions import KafkaPublishError
from rag_index.ports.kafka_port import KafkaPort

logger = logging.getLogger(__name__)


class KafkaAdapter(KafkaPort):
    """Concrete adapter for Kafka operations.

    This adapter handles publishing messages to Kafka topics
    for the rag-sync-completed and rag-sync-dlq topics.

    Configuration is loaded from Django settings:
    - KAFKA_BOOTSTRAP_SERVERS: Kafka broker addresses
    - KAFKA_COMPLETED_TOPIC: Topic for successful syncs
    - KAFKA_DLQ_TOPIC: Dead letter queue topic
    """

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        completed_topic: Optional[str] = None,
        dlq_topic: Optional[str] = None,
    ):
        """Initialize Kafka adapter.

        Args:
            bootstrap_servers: Kafka broker addresses
            completed_topic: Topic for completed events
            dlq_topic: Dead letter queue topic
        """
        self.bootstrap_servers = bootstrap_servers or getattr(
            settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self.completed_topic = completed_topic or getattr(
            settings, "KAFKA_COMPLETED_TOPIC", "rag-sync-completed"
        )
        self.dlq_topic = dlq_topic or getattr(
            settings, "KAFKA_DLQ_TOPIC", "rag-sync-dlq"
        )
        self._producer = None
        self._initialized = False

    def _get_producer(self):
        """Get or create the Kafka producer.

        Lazy initialization to avoid import errors when Kafka is not available.
        """
        if self._producer is None:
            try:
                from aiokafka import AIOKafkaProducer

                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self.bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                )
                self._initialized = True
            except ImportError:
                logger.warning(
                    "aiokafka not installed. Using mock mode for development."
                )
                self._producer = None
                self._initialized = False
        return self._producer

    async def _ensure_started(self):
        """Ensure the producer is started."""
        producer = self._get_producer()
        if producer is not None and hasattr(producer, "_sender_task"):
            if producer._sender_task is None:
                await producer.start()

    async def publish(
        self,
        topic: str,
        message: dict[str, Any],
        key: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        """Publish a message to a Kafka topic.

        Args:
            topic: The target Kafka topic
            message: The message payload
            key: Optional message key for partitioning
            headers: Optional message headers
        """
        try:
            producer = self._get_producer()

            if producer is None:
                # Mock mode for development/testing
                logger.info(
                    f"[MOCK] Publishing to {topic}: key={key}, "
                    f"message_size={len(json.dumps(message))}"
                )
                return

            await self._ensure_started()

            # Convert headers to Kafka format
            kafka_headers = None
            if headers:
                kafka_headers = [
                    (k, v.encode("utf-8") if isinstance(v, str) else v)
                    for k, v in headers.items()
                ]

            await producer.send_and_wait(
                topic=topic,
                value=message,
                key=key,
                headers=kafka_headers,
            )

            logger.debug(f"Published message to {topic}: key={key}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"Failed to publish to {topic}: {error_message}")
            raise KafkaPublishError(
                message=f"Failed to publish to Kafka: {error_message}",
                topic=topic,
            )

    async def publish_completed(
        self,
        message: dict[str, Any],
        trace_id: str,
    ) -> None:
        """Publish to the rag-sync-completed topic.

        Args:
            message: The completed event payload
            trace_id: The distributed tracing ID
        """
        headers = {"trace_id": trace_id}
        await self.publish(
            topic=self.completed_topic,
            message=message,
            key=trace_id,
            headers=headers,
        )
        logger.info(f"Published completed event: trace_id={trace_id}")

    async def publish_dlq(
        self,
        message: dict[str, Any],
        trace_id: str,
    ) -> None:
        """Publish to the rag-sync-dlq topic.

        Args:
            message: The DLQ event payload
            trace_id: The distributed tracing ID
        """
        headers = {"trace_id": trace_id}
        await self.publish(
            topic=self.dlq_topic,
            message=message,
            key=trace_id,
            headers=headers,
        )
        logger.warning(f"Published to DLQ: trace_id={trace_id}")

    async def flush(self) -> None:
        """Flush any pending messages."""
        producer = self._get_producer()
        if producer is not None:
            await producer.flush()

    async def close(self) -> None:
        """Close the Kafka producer connection."""
        if self._producer is not None:
            try:
                await self._producer.stop()
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")
            finally:
                self._producer = None
                self._initialized = False

    async def check_connection(self) -> bool:
        """Check if the Kafka connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            producer = self._get_producer()
            if producer is None:
                # Mock mode is considered healthy for development
                return True

            await self._ensure_started()
            return True
        except Exception as e:
            logger.error(f"Kafka connection check failed: {e}")
            return False
