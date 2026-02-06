"""
Kafka Adapters - Kafka implementations of EventProducerPort and EventConsumerPort.

Handles event publishing and consumption for the curation pipeline.
"""

import asyncio
import json
import logging
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import UUID

from django.conf import settings

from media_curation.ports.event_port import EventProducerPort, EventConsumerPort
from media_curation.domain.models import CurationEvent, CuratedDocument, ContentType
from media_curation.domain.exceptions import EventError


logger = logging.getLogger(__name__)

# Thread pool for async I/O operations
_executor = ThreadPoolExecutor(max_workers=4)


def _parse_tenant_id(raw_tenant_id: str) -> UUID:
    """
    Parse tenant_id from string to UUID.

    If the string is already a valid UUID, return it directly.
    Otherwise, generate a deterministic UUID from the string using UUID5.
    """
    try:
        return UUID(raw_tenant_id)
    except (ValueError, AttributeError):
        # Generate a deterministic UUID from the string using namespace
        namespace = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # DNS namespace
        return uuid.uuid5(namespace, str(raw_tenant_id))


class KafkaProducerAdapter(EventProducerPort):
    """
    Kafka producer adapter implementing EventProducerPort.

    Uses confluent-kafka for high-performance message publishing.
    """

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        client_id: str = "curation-producer",
        dlq_topic: Optional[str] = None,
        output_topic: Optional[str] = None,
        sasl_config: Optional[dict] = None,
        **kafka_config,
    ):
        """
        Initialize the Kafka producer.

        Args:
            bootstrap_servers: Kafka broker addresses (uses settings if not provided)
            client_id: Client identifier
            dlq_topic: Dead letter queue topic name
            output_topic: Default output topic for curated documents
            sasl_config: SASL/SSL config dict for managed Kafka
            **kafka_config: Additional Kafka producer config
        """
        # Lazy import to avoid issues when confluent-kafka is not installed
        try:
            from confluent_kafka import Producer

            self._kafka_available = True
        except ImportError:
            self._kafka_available = False
            logger.warning("confluent-kafka not installed, using mock mode")
            self.producer = None
            self.published_messages = []  # Mock storage
            return

        # Get Kafka config from settings
        kafka_settings = getattr(settings, "MEDIA_CURATION", {}).get("KAFKA", {})
        self.bootstrap_servers = bootstrap_servers or kafka_settings.get(
            "BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self.dlq_topic = dlq_topic or kafka_settings.get("DLQ_TOPIC", "curation-dlq")
        self.output_topic = output_topic or kafka_settings.get(
            "OUTPUT_TOPIC", "curation-completed"
        )

        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": client_id,
            "acks": "all",
            "retries": 3,
            "retry.backoff.ms": 100,
            **(sasl_config or {}),
            **kafka_config,
        }

        self.producer = Producer(config)
        logger.info(
            "Kafka producer initialized",
            extra={"bootstrap_servers": self.bootstrap_servers},
        )

    def _serialize_document(self, document: CuratedDocument) -> bytes:
        """Serialize a CuratedDocument to JSON bytes."""
        doc_dict = {
            "document_id": str(document.document_id),
            "trace_id": str(document.trace_id),
            "tenant_id": str(document.tenant_id),
            "file_id": str(document.file_id),
            "source_gcs_uri": document.source_gcs_uri,
            "output_gcs_uri": document.output_gcs_uri,
            "mime_type": document.mime_type,
            "extracted_text": document.extracted_text,
            "struct_data": document.struct_data,
            "pii_redacted": document.pii_redacted,
            "processing_time_ms": document.processing_time_ms,
            "created_at": document.created_at.isoformat(),
        }
        if document.metadata:
            doc_dict["metadata"] = document.metadata.model_dump()

        return json.dumps(doc_dict).encode("utf-8")

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

    async def publish_curated_document(
        self,
        topic: str,
        document: CuratedDocument,
        key: Optional[str] = None,
    ) -> None:
        """Publish a curated document to Kafka."""
        if not self._kafka_available:
            # Mock mode: store in memory
            self.published_messages.append(
                {
                    "topic": topic,
                    "document": document,
                    "key": key,
                }
            )
            logger.debug(f"Mock published to {topic}")
            return

        def _publish():
            try:
                key_bytes = (key or str(document.tenant_id)).encode("utf-8")
                value_bytes = self._serialize_document(document)

                self.producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=value_bytes,
                    callback=self._delivery_callback,
                    headers={
                        "trace_id": str(document.trace_id),
                        "event_type": "curation_completed",
                    },
                )
                self.producer.poll(0)

                logger.debug(
                    "Document published",
                    extra={"topic": topic, "document_id": str(document.document_id)},
                )
            except Exception as e:
                logger.error(f"Kafka publish error: {e}")
                raise EventError(f"Failed to publish document: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _publish)

    async def publish_to_dlq(
        self,
        event: CurationEvent,
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """Publish failed event to dead letter queue."""
        if not self._kafka_available:
            # Mock mode: store in memory
            self.published_messages.append(
                {
                    "topic": self.dlq_topic,
                    "event": event,
                    "error": str(error),
                    "retry_count": retry_count,
                }
            )
            logger.debug(f"Mock published to DLQ: {self.dlq_topic}")
            return

        def _publish():
            try:
                dlq_payload = {
                    "original_event": {
                        "event_id": str(event.event_id),
                        "trace_id": str(event.trace_id),
                        "tenant_id": str(event.tenant_id),
                        "file_id": str(event.file_id),
                        "raw_gcs_uri": event.raw_gcs_uri,
                        "mime_type": event.mime_type,
                        "content_type": event.content_type.value,
                        "timestamp": event.timestamp.isoformat(),
                    },
                    "error": {
                        "message": str(error),
                        "type": type(error).__name__,
                        "traceback": traceback.format_exc(),
                    },
                    "retry_count": retry_count,
                    "dlq_timestamp": datetime.now(timezone.utc).isoformat(),
                }

                self.producer.produce(
                    topic=self.dlq_topic,
                    key=str(event.tenant_id).encode("utf-8"),
                    value=json.dumps(dlq_payload).encode("utf-8"),
                    callback=self._delivery_callback,
                    headers={
                        "trace_id": str(event.trace_id),
                        "event_type": "curation_failed",
                        "error_type": type(error).__name__,
                    },
                )
                self.producer.poll(0)

                logger.warning(
                    "Event sent to DLQ",
                    extra={
                        "trace_id": str(event.trace_id),
                        "error": str(error),
                        "retry_count": retry_count,
                    },
                )
            except Exception as e:
                logger.error(f"Failed to publish to DLQ: {e}")
                raise EventError(f"Failed to publish to DLQ: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _publish)

    async def publish_raw(
        self,
        topic: str,
        payload: dict[str, Any],
        key: Optional[str] = None,
    ) -> None:
        """Publish raw dict payload to Kafka."""
        if not self._kafka_available:
            self.published_messages.append(
                {
                    "topic": topic,
                    "payload": payload,
                    "key": key,
                }
            )
            return

        def _publish():
            try:
                key_bytes = key.encode("utf-8") if key else None
                value_bytes = json.dumps(payload).encode("utf-8")

                self.producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=value_bytes,
                    callback=self._delivery_callback,
                )
                self.producer.poll(0)
            except Exception as e:
                logger.error(f"Kafka publish error: {e}")
                raise EventError(f"Failed to publish message: {e}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _publish)

    def flush(self, timeout: float = 10.0) -> int:
        """Wait for all messages to be delivered."""
        if not self._kafka_available:
            return 0

        return self.producer.flush(timeout)


class KafkaConsumerAdapter(EventConsumerPort):
    """
    Kafka consumer adapter implementing EventConsumerPort.

    Uses confluent-kafka for message consumption.
    """

    def __init__(
        self,
        bootstrap_servers: Optional[str] = None,
        group_id: str = "curation-consumer",
        input_topic: Optional[str] = None,
        auto_commit: bool = False,
        sasl_config: Optional[dict] = None,
        **kafka_config,
    ):
        """
        Initialize the Kafka consumer.

        Args:
            bootstrap_servers: Kafka broker addresses
            group_id: Consumer group ID
            input_topic: Default input topic to subscribe to
            auto_commit: Enable auto-commit (False for manual commits)
            sasl_config: SASL/SSL config dict for managed Kafka
            **kafka_config: Additional Kafka consumer config
        """
        # Lazy import to avoid issues when confluent-kafka is not installed
        try:
            from confluent_kafka import Consumer

            self._kafka_available = True
        except ImportError:
            self._kafka_available = False
            logger.warning("confluent-kafka not installed, using mock mode")
            self.consumer = None
            self._mock_messages = []
            self._mock_position = 0
            return

        # Get Kafka config from settings
        kafka_settings = getattr(settings, "MEDIA_CURATION", {}).get("KAFKA", {})
        self.bootstrap_servers = bootstrap_servers or kafka_settings.get(
            "BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self.input_topic = input_topic or kafka_settings.get(
            "INPUT_TOPIC", "curation-needed"
        )

        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": auto_commit,
            **(sasl_config or {}),
            **kafka_config,
        }

        self.consumer = Consumer(config)
        logger.info(
            "Kafka consumer initialized",
            extra={"bootstrap_servers": self.bootstrap_servers, "group_id": group_id},
        )

    def _deserialize_event(self, value: bytes) -> CurationEvent:
        """Deserialize JSON bytes to CurationEvent."""
        data = json.loads(value.decode("utf-8"))

        # Handle nested CloudEvent format
        if "data" in data:
            event_data = data["data"]
        else:
            event_data = data

        # Parse content_type with case-insensitive handling
        raw_content_type = event_data.get("content_type", "").lower() or "unknown"
        try:
            content_type = ContentType(raw_content_type)
        except ValueError:
            # If invalid content_type, we'll infer from mime_type later
            content_type = ContentType.UNKNOWN

        # Get event_id - required
        event_id = UUID(event_data.get("event_id", data.get("id", str(UUID(int=0)))))

        # Handle backward compatibility with old message format:
        # - file_id: Use file_id if present, else fallback to event_id
        # - raw_gcs_uri: Use raw_gcs_uri if present, else destination_path
        # - mime_type: Use if present, else file_metadata.content_type
        file_id = UUID(event_data.get("file_id", str(event_id)))

        raw_gcs_uri = event_data.get("raw_gcs_uri") or event_data.get(
            "destination_path"
        )
        if not raw_gcs_uri:
            raise KeyError("raw_gcs_uri or destination_path required")

        mime_type = event_data.get("mime_type")
        if not mime_type:
            # Try to get from file_metadata
            file_metadata = event_data.get("file_metadata", {})
            mime_type = file_metadata.get("content_type", "application/octet-stream")

        event = CurationEvent(
            event_id=event_id,
            trace_id=UUID(event_data.get("trace_id", str(UUID(int=0)))),
            tenant_id=_parse_tenant_id(event_data["tenant_id"]),
            file_id=file_id,
            raw_gcs_uri=raw_gcs_uri,
            mime_type=mime_type,
            content_type=content_type,
            source_service=event_data.get("source_service", "data-ingestion"),
            timestamp=datetime.fromisoformat(
                event_data.get("timestamp", datetime.now(timezone.utc).isoformat())
            ),
            metadata=event_data.get("metadata", {}),
        )

        # If content_type is unknown, infer from mime_type
        if event.content_type == ContentType.UNKNOWN:
            event.content_type = event.get_content_type()

        return event

    def subscribe(self, topics: Optional[list[str]] = None) -> None:
        """Subscribe to Kafka topics."""
        if not self._kafka_available:
            logger.debug(f"Mock subscribed to topics: {topics or [self.input_topic]}")
            return

        topic_list = topics or [self.input_topic]
        self.consumer.subscribe(topic_list)
        logger.info(f"Subscribed to topics: {topic_list}")

    async def consume_one(
        self,
        timeout: float = 1.0,
    ) -> Optional[CurationEvent]:
        """Consume a single message."""
        if not self._kafka_available:
            if self._mock_position < len(self._mock_messages):
                msg = self._mock_messages[self._mock_position]
                self._mock_position += 1
                return msg
            return None

        def _consume():
            try:
                msg = self.consumer.poll(timeout)
                if msg is None:
                    return None
                if msg.error():
                    from confluent_kafka import KafkaError

                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        return None
                    raise EventError(f"Kafka consume error: {msg.error()}")

                return self._deserialize_event(msg.value())

            except Exception as e:
                logger.error(f"Kafka consume error: {e}")
                raise EventError(f"Failed to consume message: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _consume)

    async def consume_batch(
        self,
        max_messages: int = 100,
        timeout: float = 1.0,
    ) -> list[CurationEvent]:
        """Consume a batch of messages."""
        if not self._kafka_available:
            batch = []
            for _ in range(max_messages):
                if self._mock_position < len(self._mock_messages):
                    batch.append(self._mock_messages[self._mock_position])
                    self._mock_position += 1
                else:
                    break
            return batch

        def _consume_batch():
            try:
                events = []
                for _ in range(max_messages):
                    msg = self.consumer.poll(timeout)
                    if msg is None:
                        break
                    if msg.error():
                        from confluent_kafka import KafkaError

                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        logger.warning(f"Kafka error: {msg.error()}")
                        continue

                    events.append(self._deserialize_event(msg.value()))

                return events

            except Exception as e:
                logger.error(f"Kafka batch consume error: {e}")
                raise EventError(f"Failed to consume batch: {e}")

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _consume_batch)

    def commit(self, asynchronous: bool = True) -> None:
        """Commit current offsets."""
        if not self._kafka_available:
            return

        try:
            self.consumer.commit(asynchronous=asynchronous)
        except Exception as e:
            logger.error(f"Kafka commit error: {e}")
            raise EventError(f"Failed to commit offsets: {e}")

    def close(self) -> None:
        """Close the consumer."""
        if self._kafka_available and self.consumer:
            self.consumer.close()
            logger.info("Kafka consumer closed")

    async def is_healthy(self) -> bool:
        """Check if Kafka consumer is connected."""
        if not self._kafka_available:
            return True  # Mock mode is always "healthy"

        def _check():
            try:
                # Get cluster metadata as health check
                metadata = self.consumer.list_topics(timeout=5)
                return metadata is not None
            except Exception as e:
                logger.warning(f"Kafka health check failed: {e}")
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _check)
