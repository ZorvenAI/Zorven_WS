"""
Kafka Port.

Abstract interface for publishing messages to Kafka topics.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class KafkaPort(ABC):
    """Abstract interface for Kafka operations.

    This port defines the contract for publishing messages to Kafka topics,
    including the completed and DLQ topics.
    """

    @abstractmethod
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
            message: The message payload (will be JSON serialized)
            key: Optional message key for partitioning
            headers: Optional message headers

        Raises:
            KafkaPublishError: If publishing fails
        """

    @abstractmethod
    async def publish_completed(
        self,
        message: dict[str, Any],
        trace_id: str,
    ) -> None:
        """Publish to the rag-sync-completed topic.

        Args:
            message: The completed event payload
            trace_id: The distributed tracing ID

        Raises:
            KafkaPublishError: If publishing fails
        """

    @abstractmethod
    async def publish_dlq(
        self,
        message: dict[str, Any],
        trace_id: str,
    ) -> None:
        """Publish to the rag-sync-dlq (dead letter queue) topic.

        Args:
            message: The DLQ event payload
            trace_id: The distributed tracing ID

        Raises:
            KafkaPublishError: If publishing fails
        """

    @abstractmethod
    async def flush(self) -> None:
        """Flush any pending messages.

        Ensures all buffered messages are sent before returning.
        """

    @abstractmethod
    async def close(self) -> None:
        """Close the Kafka producer connection."""

    @abstractmethod
    async def check_connection(self) -> bool:
        """Check if the Kafka connection is healthy.

        Returns:
            True if connection is healthy, False otherwise
        """
