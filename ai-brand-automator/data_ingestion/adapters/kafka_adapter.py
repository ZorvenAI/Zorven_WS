"""
Kafka Adapters - Kafka implementations of EventProducerPort and EventConsumerPort.

Handles event publishing and consumption for the ingestion pipeline.
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Callable
from uuid import UUID

from confluent_kafka import Producer, Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient

from data_ingestion.ports.event_port import EventProducerPort, EventConsumerPort
from data_ingestion.domain.models import IngestionEvent, ProcessedEvent
from data_ingestion.domain.exceptions import (
    EventPublishError,
    EventConsumptionError,
    InvalidEventError,
)


logger = logging.getLogger(__name__)


class KafkaProducerAdapter(EventProducerPort):
    """
    Kafka producer adapter implementing EventProducerPort.

    Uses confluent-kafka for high-performance message publishing.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        client_id: str = "ingestion-producer",
        acks: str = "all",
        retries: int = 3,
        retry_backoff_ms: int = 100,
        dlq_topic: Optional[str] = None,
        **kafka_config,
    ):
        """
        Initialize the Kafka producer.

        Args:
            bootstrap_servers: Kafka broker addresses
            client_id: Client identifier
            acks: Acknowledgment level ('all', '1', '0')
            retries: Number of retries for failed sends
            retry_backoff_ms: Backoff between retries
            dlq_topic: Dead letter queue topic name
            **kafka_config: Additional Kafka producer config
        """
        self.bootstrap_servers = bootstrap_servers
        self.dlq_topic = dlq_topic

        config = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
            "acks": acks,
            "retries": retries,
            "retry.backoff.ms": retry_backoff_ms,
            **kafka_config,
        }

        self.producer = Producer(config)
        logger.info(
            "Kafka producer initialized",
            extra={"bootstrap_servers": bootstrap_servers, "client_id": client_id},
        )

    def _serialize_event(self, event: ProcessedEvent) -> bytes:
        """Serialize a ProcessedEvent to JSON bytes."""
        event_dict = {
            "event_id": str(event.event_id),
            "trace_id": str(event.trace_id),
            "timestamp": event.timestamp.isoformat(),
            "tenant_id": event.tenant_id,
            "source_path": event.source_path,
            "destination_path": event.destination_path,
            "status": event.status.value,
            "processing_duration_ms": event.processing_duration_ms,
        }
        if event.error_message:
            event_dict["error_message"] = event.error_message
        if event.file_metadata:
            event_dict["file_metadata"] = event.file_metadata.model_dump()

        return json.dumps(event_dict).encode("utf-8")

    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation."""
        if err:
            logger.error(
                "Message delivery failed",
                extra={"error": str(err), "topic": msg.topic()},
            )
        else:
            logger.debug(
                "Message delivered",
                extra={
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )

    def publish(
        self,
        topic: str,
        event: ProcessedEvent,
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a processed event to a Kafka topic.

        Args:
            topic: Target Kafka topic
            event: The ProcessedEvent to publish
            key: Optional partition key (defaults to tenant_id)

        Raises:
            EventPublishError: If publishing fails
        """
        try:
            key_bytes = (key or event.tenant_id).encode("utf-8")
            value_bytes = self._serialize_event(event)

            self.producer.produce(
                topic=topic,
                key=key_bytes,
                value=value_bytes,
                callback=self._delivery_callback,
                headers={
                    "trace_id": str(event.trace_id),
                    "event_type": "processed_event",
                },
            )

            # Trigger delivery callbacks
            self.producer.poll(0)

            logger.debug(
                "Event published",
                extra={
                    "topic": topic,
                    "event_id": str(event.event_id),
                    "trace_id": str(event.trace_id),
                },
            )
        except KafkaException as e:
            logger.error(
                "Failed to publish event",
                extra={
                    "topic": topic,
                    "event_id": str(event.event_id),
                    "error": str(e),
                },
            )
            raise EventPublishError(
                topic=topic,
                event_id=event.event_id,
                cause=e,
            )

    def publish_raw(
        self,
        topic: str,
        payload: dict,
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a raw dict payload to a Kafka topic.

        Args:
            topic: Target Kafka topic
            payload: Dict payload to publish (will be JSON serialized)
            key: Optional partition key

        Raises:
            EventPublishError: If publishing fails
        """
        try:
            key_bytes = key.encode("utf-8") if key else None
            value_bytes = json.dumps(payload).encode("utf-8")

            self.producer.produce(
                topic=topic,
                key=key_bytes,
                value=value_bytes,
                callback=self._delivery_callback,
            )

            # Trigger delivery callbacks
            self.producer.poll(0)

            logger.debug(
                "Raw payload published",
                extra={"topic": topic},
            )
        except KafkaException as e:
            logger.error(
                "Failed to publish raw payload",
                extra={"topic": topic, "error": str(e)},
            )
            raise EventPublishError(
                topic=topic,
                cause=e,
            )

    def publish_to_dlq(
        self,
        original_event: dict,
        error: Exception,
        source_topic: str,
    ) -> None:
        """
        Publish a failed event to the Dead Letter Queue.

        Args:
            original_event: The original event that failed
            error: The exception that caused the failure
            source_topic: The topic the event came from

        Raises:
            EventPublishError: If DLQ publishing fails
        """
        if not self.dlq_topic:
            logger.warning("No DLQ topic configured, cannot publish failed event")
            return

        try:
            dlq_message = {
                "original_event": original_event,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                    "traceback": traceback.format_exc(),
                },
                "source_topic": source_topic,
                "failed_at": datetime.utcnow().isoformat(),
            }

            # Extract key if available
            key = original_event.get("tenant_id", "unknown")

            self.producer.produce(
                topic=self.dlq_topic,
                key=key.encode("utf-8"),
                value=json.dumps(dlq_message).encode("utf-8"),
                callback=self._delivery_callback,
                headers={
                    "error_type": type(error).__name__,
                    "source_topic": source_topic,
                },
            )

            self.producer.poll(0)

            logger.info(
                "Event sent to DLQ",
                extra={
                    "dlq_topic": self.dlq_topic,
                    "source_topic": source_topic,
                    "error_type": type(error).__name__,
                },
            )
        except KafkaException as e:
            logger.error(
                "Failed to publish to DLQ",
                extra={"dlq_topic": self.dlq_topic, "error": str(e)},
            )
            raise EventPublishError(
                topic=self.dlq_topic,
                cause=e,
            )

    def flush(self, timeout: float = 10.0) -> int:
        """
        Flush all pending messages.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Number of messages still in queue (0 if all flushed)
        """
        return self.producer.flush(timeout)

    def close(self) -> None:
        """Close the producer and flush pending messages."""
        self.flush()
        logger.info("Kafka producer closed")


class KafkaConsumerAdapter(EventConsumerPort):
    """
    Kafka consumer adapter implementing EventConsumerPort.

    Uses confluent-kafka for high-performance message consumption.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        client_id: str = "ingestion-consumer",
        auto_offset_reset: str = "earliest",
        enable_auto_commit: bool = False,
        max_poll_interval_ms: int = 300000,
        session_timeout_ms: int = 45000,
        **kafka_config,
    ):
        """
        Initialize the Kafka consumer.

        Args:
            bootstrap_servers: Kafka broker addresses
            group_id: Consumer group ID
            topics: List of topics to subscribe to
            client_id: Client identifier
            auto_offset_reset: Where to start if no offset ('earliest', 'latest')
            enable_auto_commit: Whether to auto-commit offsets
            max_poll_interval_ms: Max time between polls
            session_timeout_ms: Session timeout
            **kafka_config: Additional Kafka consumer config
        """
        self.bootstrap_servers = bootstrap_servers
        self.group_id = group_id
        self.topics = topics
        self._running = False
        self._message_handler: Optional[Callable[[IngestionEvent], None]] = None

        config = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "client.id": client_id,
            "auto.offset.reset": auto_offset_reset,
            "enable.auto.commit": enable_auto_commit,
            "max.poll.interval.ms": max_poll_interval_ms,
            "session.timeout.ms": session_timeout_ms,
            **kafka_config,
        }

        self.consumer = Consumer(config)
        logger.info(
            "Kafka consumer initialized",
            extra={
                "bootstrap_servers": bootstrap_servers,
                "group_id": group_id,
                "topics": topics,
            },
        )

    def _deserialize_event(self, value: bytes) -> IngestionEvent:
        """Deserialize JSON bytes to an IngestionEvent."""
        try:
            data = json.loads(value.decode("utf-8"))

            # Parse UUID fields
            data["event_id"] = UUID(data["event_id"])
            if "trace_id" in data and data["trace_id"]:
                data["trace_id"] = UUID(data["trace_id"])

            # Parse timestamp
            if isinstance(data.get("timestamp"), str):
                data["timestamp"] = datetime.fromisoformat(
                    data["timestamp"].replace("Z", "+00:00")
                )

            return IngestionEvent(**data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise InvalidEventError(
                reason=f"Failed to deserialize event: {e}",
                raw_event=value.decode("utf-8", errors="replace"),
            )

    def subscribe(self, topics: Optional[list[str]] = None) -> None:
        """
        Subscribe to Kafka topics.

        Args:
            topics: List of topics (uses configured topics if not provided)
        """
        topics = topics or self.topics
        self.consumer.subscribe(topics)
        logger.info("Subscribed to topics", extra={"topics": topics})

    def poll(self, timeout_seconds: float = 1.0) -> Optional[dict]:
        """
        Poll for the next message.

        Args:
            timeout_seconds: Maximum time to wait for a message

        Returns:
            Message dict with 'key', 'value', 'topic', 'partition', 'offset'
            or None if no message available

        Raises:
            EventConsumptionError: If polling fails
        """
        try:
            msg = self.consumer.poll(timeout_seconds)

            if msg is None:
                return None

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    return None
                raise EventConsumptionError(
                    topic=msg.topic(),
                    cause=KafkaException(msg.error()),
                )

            return {
                "key": msg.key().decode("utf-8") if msg.key() else None,
                "value": json.loads(msg.value().decode("utf-8"))
                if msg.value()
                else None,
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
            }

        except KafkaException as e:
            raise EventConsumptionError(cause=e)

    def seek_to_beginning(self) -> None:
        """
        Seek to the beginning of all subscribed partitions.

        Raises:
            EventConsumptionError: If seek fails
        """
        try:
            # Get assigned partitions
            partitions = self.consumer.assignment()
            if partitions:
                # Seek each partition to beginning
                for partition in partitions:
                    partition.offset = 0
                self.consumer.assign(partitions)
            logger.info("Seeked to beginning of all partitions")
        except KafkaException as e:
            raise EventConsumptionError(cause=e)

    def consume_one(self, timeout: float = 1.0) -> Optional[IngestionEvent]:
        """
        Consume a single message.

        Args:
            timeout: How long to wait for a message

        Returns:
            IngestionEvent if message received, None if timeout

        Raises:
            EventConsumptionError: If there's a Kafka error
            InvalidEventError: If message can't be deserialized
        """
        try:
            msg = self.consumer.poll(timeout)

            if msg is None:
                return None

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    # End of partition, not an error
                    return None
                raise EventConsumptionError(
                    topic=msg.topic(),
                    cause=KafkaException(msg.error()),
                )

            event = self._deserialize_event(msg.value())

            logger.debug(
                "Message consumed",
                extra={
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "event_id": str(event.event_id),
                },
            )

            return event

        except InvalidEventError:
            raise
        except KafkaException as e:
            raise EventConsumptionError(cause=e)

    def consume_batch(
        self,
        max_messages: int = 100,
        timeout: float = 1.0,
    ) -> list[IngestionEvent]:
        """
        Consume a batch of messages.

        Args:
            max_messages: Maximum messages to consume
            timeout: How long to wait for messages

        Returns:
            List of IngestionEvents

        Raises:
            EventConsumptionError: If there's a Kafka error
        """
        events = []
        try:
            messages = self.consumer.consume(max_messages, timeout)

            for msg in messages:
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise EventConsumptionError(
                        topic=msg.topic(),
                        cause=KafkaException(msg.error()),
                    )

                try:
                    event = self._deserialize_event(msg.value())
                    events.append(event)
                except InvalidEventError as e:
                    logger.warning(
                        "Skipping invalid event",
                        extra={"error": str(e), "offset": msg.offset()},
                    )
                    continue

            return events

        except KafkaException as e:
            raise EventConsumptionError(cause=e)

    def start_consuming(
        self,
        handler: Callable[[IngestionEvent], None],
        poll_timeout: float = 1.0,
    ) -> None:
        """
        Start consuming messages in a loop.

        Args:
            handler: Callback function to process each event
            poll_timeout: Timeout for each poll
        """
        self._message_handler = handler
        self._running = True
        self.subscribe()

        logger.info("Starting consumer loop")

        while self._running:
            try:
                event = self.consume_one(poll_timeout)
                if event:
                    try:
                        handler(event)
                        self.commit()
                    except Exception as e:
                        logger.error(
                            "Handler error",
                            extra={
                                "event_id": str(event.event_id),
                                "error": str(e),
                            },
                        )
                        # Don't commit on error - let it be redelivered
            except EventConsumptionError as e:
                logger.error("Consumption error", extra={"error": str(e)})
            except InvalidEventError as e:
                logger.warning("Invalid event, skipping", extra={"error": str(e)})
                self.commit()  # Commit to skip invalid event

    def stop_consuming(self) -> None:
        """Stop the consumer loop."""
        self._running = False
        logger.info("Consumer loop stopping")

    def commit(self, asynchronous: bool = False) -> None:
        """
        Commit current offsets.

        Args:
            asynchronous: Whether to commit asynchronously
        """
        try:
            self.consumer.commit(asynchronous=asynchronous)
        except KafkaException as e:
            logger.error("Failed to commit offsets", extra={"error": str(e)})
            raise EventConsumptionError(cause=e)

    def close(self) -> None:
        """Close the consumer."""
        self.stop_consuming()
        self.consumer.close()
        logger.info("Kafka consumer closed")

    def health_check(self) -> bool:
        """
        Check if Kafka connection is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # List topics to verify connection
            admin = AdminClient({"bootstrap.servers": self.bootstrap_servers})
            metadata = admin.list_topics(timeout=5)
            return len(metadata.topics) >= 0
        except Exception:
            return False
