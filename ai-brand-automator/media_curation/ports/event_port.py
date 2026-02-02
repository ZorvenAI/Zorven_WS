"""
Event Port.

Abstract interface for event streaming (Kafka).
Reuses patterns from data_ingestion.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any

from media_curation.domain.models import CurationEvent, CuratedDocument


class EventProducerPort(ABC):
    """
    Abstract interface for publishing events to Kafka.
    """

    @abstractmethod
    async def publish_curated_document(
        self,
        topic: str,
        document: CuratedDocument,
        key: Optional[str] = None,
    ) -> None:
        """
        Publish a curated document to Kafka.

        Args:
            topic: Target Kafka topic
            document: The curated document
            key: Optional partition key (defaults to tenant_id)
        """
        pass

    @abstractmethod
    async def publish_to_dlq(
        self,
        event: CurationEvent,
        error: Exception,
        retry_count: int = 0,
    ) -> None:
        """
        Publish failed event to dead letter queue.

        Args:
            event: The original event that failed
            error: The exception that caused failure
            retry_count: Number of retries attempted
        """
        pass

    @abstractmethod
    async def publish_raw(
        self,
        topic: str,
        payload: dict[str, Any],
        key: Optional[str] = None,
    ) -> None:
        """
        Publish raw dict payload to Kafka.

        Args:
            topic: Target topic
            payload: Dict to publish (JSON serialized)
            key: Optional partition key
        """
        pass

    @abstractmethod
    def flush(self, timeout: float = 10.0) -> int:
        """
        Wait for all messages to be delivered.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            Number of messages still in queue
        """
        pass


class EventConsumerPort(ABC):
    """
    Abstract interface for consuming events from Kafka.
    """

    @abstractmethod
    def subscribe(self, topics: Optional[list[str]] = None) -> None:
        """
        Subscribe to Kafka topics.

        Args:
            topics: List of topics (uses configured topics if not provided)
        """
        pass

    @abstractmethod
    async def consume_one(
        self,
        timeout: float = 1.0,
    ) -> Optional[CurationEvent]:
        """
        Consume a single message.

        Args:
            timeout: Maximum wait time

        Returns:
            CurationEvent or None if no message available
        """
        pass

    @abstractmethod
    async def consume_batch(
        self,
        max_messages: int = 100,
        timeout: float = 1.0,
    ) -> list[CurationEvent]:
        """
        Consume a batch of messages.

        Args:
            max_messages: Maximum messages to consume
            timeout: Maximum wait time

        Returns:
            List of CurationEvents
        """
        pass

    @abstractmethod
    def commit(self, asynchronous: bool = True) -> None:
        """
        Commit current offsets.

        Args:
            asynchronous: Whether to commit asynchronously
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the consumer."""
        pass

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if Kafka consumer is connected."""
        pass
