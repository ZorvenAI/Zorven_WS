"""
Event Port - Abstract interface for event publishing (Kafka).

This port defines how the domain layer publishes events to message queues.
"""

from abc import ABC, abstractmethod
from typing import Optional

from data_ingestion.domain.models import ProcessedEvent


class EventProducerPort(ABC):
    """
    Abstract interface for publishing events to a message queue.

    Implementations:
        - KafkaProducerAdapter: Kafka implementation
        - MockEventProducerAdapter: For testing
    """

    @abstractmethod
    def publish(
        self,
        topic: str,
        event: ProcessedEvent,
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a processed event to the specified topic.

        Args:
            topic: Target topic name
            event: ProcessedEvent to publish
            key: Optional partition key (defaults to event.tenant_id)

        Raises:
            EventPublishError: If publishing fails
        """
        pass

    @abstractmethod
    def publish_raw(
        self,
        topic: str,
        payload: dict,
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a raw dict payload to the specified topic.

        Args:
            topic: Target topic name
            payload: Dict payload to publish (will be JSON serialized)
            key: Optional partition key

        Raises:
            EventPublishError: If publishing fails
        """
        pass

    @abstractmethod
    def publish_to_dlq(
        self,
        original_event: dict,
        error: Exception,
        source_topic: str,
    ) -> None:
        """
        Publish a failed event to the Dead Letter Queue.

        Wraps the original event with error information.

        Args:
            original_event: The original event that failed processing
            error: The exception that caused the failure
            source_topic: The topic the original event came from

        Raises:
            EventPublishError: If publishing to DLQ fails
        """
        pass

    @abstractmethod
    def flush(self, timeout_seconds: float = 10.0) -> int:
        """
        Flush any pending messages.

        Blocks until all messages are delivered or timeout expires.

        Args:
            timeout_seconds: Maximum time to wait for flush

        Returns:
            Number of messages still in queue (0 if all delivered)

        Raises:
            EventPublishError: If flush fails
        """
        pass


class EventConsumerPort(ABC):
    """
    Abstract interface for consuming events from a message queue.

    Implementations:
        - KafkaConsumerAdapter: Kafka implementation
        - MockEventConsumerAdapter: For testing
    """

    @abstractmethod
    def poll(self, timeout_seconds: float = 1.0) -> Optional[dict]:
        """
        Poll for the next message.

        Args:
            timeout_seconds: Maximum time to wait for a message

        Returns:
            Message dict with 'key', 'value', 'topic', 'partition', 'offset'
            or None if no message available

        Raises:
            EventConsumerError: If polling fails
        """
        pass

    @abstractmethod
    def commit(self) -> None:
        """
        Commit the current offset.

        Should only be called after successful processing.

        Raises:
            EventConsumerError: If commit fails
        """
        pass

    @abstractmethod
    def subscribe(self, topics: Optional[list[str]] = None) -> None:
        """
        Subscribe to topics for this consumer.

        Implementations may determine the topics from constructor
        arguments, settings, or other configuration. If topics is
        provided, it overrides the configured topics.

        Args:
            topics: Optional list of topic names to subscribe to.
                    If not provided, uses topics configured at construction.

        Raises:
            EventConsumerError: If subscription fails
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the consumer and release resources.

        Should be called when the consumer is no longer needed.
        """
        pass

    @abstractmethod
    def seek_to_beginning(self) -> None:
        """
        Seek to the beginning of all subscribed partitions.

        Useful for reprocessing or testing.

        Raises:
            EventConsumerError: If seek fails
        """
        pass
