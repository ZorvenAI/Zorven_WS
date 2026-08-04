"""
Consumer Health Tracking for Media Curation.

Provides a mechanism for the Kafka consumer management command to report
its health status, which can be queried by the health check endpoint.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ConsumerHealthStatus:
    """Health status of a consumer instance."""

    instance_id: str
    status: str = "starting"  # starting, running, stopping, stopped, error
    last_heartbeat: Optional[datetime] = None
    events_processed: int = 0
    events_failed: int = 0
    last_event_time: Optional[datetime] = None
    current_batch_size: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "instance_id": self.instance_id,
            "status": self.status,
            "last_heartbeat": (
                self.last_heartbeat.isoformat() if self.last_heartbeat else None
            ),
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "last_event_time": (
                self.last_event_time.isoformat() if self.last_event_time else None
            ),
            "current_batch_size": self.current_batch_size,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "uptime_seconds": (
                (datetime.utcnow() - self.started_at).total_seconds()
                if self.started_at
                else 0
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsumerHealthStatus":
        """Create from dictionary."""
        return cls(
            instance_id=data.get("instance_id", "unknown"),
            status=data.get("status", "unknown"),
            last_heartbeat=(
                datetime.fromisoformat(data["last_heartbeat"])
                if data.get("last_heartbeat")
                else None
            ),
            events_processed=data.get("events_processed", 0),
            events_failed=data.get("events_failed", 0),
            last_event_time=(
                datetime.fromisoformat(data["last_event_time"])
                if data.get("last_event_time")
                else None
            ),
            current_batch_size=data.get("current_batch_size", 0),
            error_message=data.get("error_message"),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else None
            ),
        )


class ConsumerHealthTracker:
    """
    Tracks and reports consumer health status.

    Uses Redis to store health status so it can be queried by the health endpoint.
    Each consumer instance registers itself and periodically updates its heartbeat.
    """

    # Redis key prefix for consumer health
    HEALTH_KEY_PREFIX = "media_curation:consumer:health:"

    # TTL for health entries
    # (consumers are considered dead if not updated within this time)
    HEALTH_TTL_SECONDS = 60

    # Heartbeat interval - how often consumers should update their status
    HEARTBEAT_INTERVAL_SECONDS = 15

    def __init__(self, redis_client, instance_id: str):
        """
        Initialize the health tracker.

        Args:
            redis_client: Redis client instance (can be async or sync)
            instance_id: Unique identifier for this consumer instance
        """
        self._redis = redis_client
        self._instance_id = instance_id
        self._status = ConsumerHealthStatus(
            instance_id=instance_id,
            started_at=datetime.utcnow(),
        )
        self._last_heartbeat_time = 0
        self._redis_available = True

    @property
    def key(self) -> str:
        """Redis key for this consumer instance."""
        return f"{self.HEALTH_KEY_PREFIX}{self._instance_id}"

    def update_status(
        self,
        status: Optional[str] = None,
        events_processed: Optional[int] = None,
        events_failed: Optional[int] = None,
        current_batch_size: Optional[int] = None,
        error_message: Optional[str] = None,
        event_processed: bool = False,
    ) -> None:
        """
        Update the consumer health status.

        Args:
            status: Consumer status (starting, running, stopping, stopped, error)
            events_processed: Total events processed
            events_failed: Total events failed
            current_batch_size: Current batch being processed
            error_message: Error message if any
            event_processed: If True, updates last_event_time to now
        """
        if status is not None:
            self._status.status = status
        if events_processed is not None:
            self._status.events_processed = events_processed
        if events_failed is not None:
            self._status.events_failed = events_failed
        if current_batch_size is not None:
            self._status.current_batch_size = current_batch_size
        if error_message is not None:
            self._status.error_message = error_message
        if event_processed:
            self._status.last_event_time = datetime.utcnow()

        # Always update heartbeat on status change
        self._status.last_heartbeat = datetime.utcnow()

        # Persist to Redis
        self._persist_status()

    def heartbeat(self) -> None:
        """
        Send a heartbeat to indicate the consumer is alive.

        Only actually persists if enough time has passed since last heartbeat.
        """
        now = time.time()
        if now - self._last_heartbeat_time >= self.HEARTBEAT_INTERVAL_SECONDS:
            self._status.last_heartbeat = datetime.utcnow()
            self._persist_status()
            self._last_heartbeat_time = now

    def increment_processed(self) -> None:
        """Increment the events processed counter."""
        self._status.events_processed += 1
        self._status.last_event_time = datetime.utcnow()

    def increment_failed(self) -> None:
        """Increment the events failed counter."""
        self._status.events_failed += 1

    def _persist_status(self) -> None:
        """Persist the current status to Redis."""
        if not self._redis_available:
            return

        try:
            status_json = json.dumps(self._status.to_dict())

            # Check if redis client is async
            if hasattr(self._redis, "__aenter__"):
                # For async clients, we need to use sync workaround
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if loop.is_running():
                    # Can't run async in sync context when loop is running
                    # Fall back to fire-and-forget
                    asyncio.ensure_future(self._async_set(status_json))
                else:
                    loop.run_until_complete(self._async_set(status_json))
            else:
                # Sync redis client
                self._redis.setex(
                    self.key,
                    self.HEALTH_TTL_SECONDS,
                    status_json,
                )
        except Exception as e:
            logger.warning(f"Failed to persist consumer health: {e}")
            self._redis_available = False

    async def _async_set(self, status_json: str) -> None:
        """Async version of set operation."""
        try:
            await self._redis.setex(
                self.key,
                self.HEALTH_TTL_SECONDS,
                status_json,
            )
        except Exception as e:
            logger.warning(f"Failed to persist consumer health (async): {e}")
            self._redis_available = False

    def cleanup(self) -> None:
        """Remove the health entry when consumer shuts down."""
        if not self._redis_available:
            return

        try:
            if hasattr(self._redis, "__aenter__"):
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                if not loop.is_running():
                    loop.run_until_complete(self._redis.delete(self.key))
            else:
                self._redis.delete(self.key)
        except Exception as e:
            logger.warning(f"Failed to cleanup consumer health: {e}")

    @classmethod
    def get_all_consumers(cls, redis_client) -> list[ConsumerHealthStatus]:
        """
        Get health status of all registered consumers.

        Args:
            redis_client: Redis client instance

        Returns:
            List of ConsumerHealthStatus for all active consumers
        """
        try:
            # Get all consumer health keys
            pattern = f"{cls.HEALTH_KEY_PREFIX}*"

            if hasattr(redis_client, "__aenter__"):
                # Async client - return empty for now, will be handled by async caller
                return []
            else:
                keys = redis_client.keys(pattern)
                consumers = []

                for key in keys:
                    try:
                        data = redis_client.get(key)
                        if data:
                            status_dict = json.loads(data)
                            consumers.append(
                                ConsumerHealthStatus.from_dict(status_dict)
                            )
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse consumer health for {key}: {e}"
                        )

                return consumers
        except Exception as e:
            logger.warning(f"Failed to get consumer health statuses: {e}")
            return []

    @classmethod
    async def get_all_consumers_async(cls, redis_client) -> list[ConsumerHealthStatus]:
        """
        Async version to get health status of all registered consumers.

        Args:
            redis_client: Async Redis client instance

        Returns:
            List of ConsumerHealthStatus for all active consumers
        """
        try:
            pattern = f"{cls.HEALTH_KEY_PREFIX}*"
            keys = await redis_client.keys(pattern)
            consumers = []

            for key in keys:
                try:
                    data = await redis_client.get(key)
                    if data:
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")
                        status_dict = json.loads(data)
                        consumers.append(ConsumerHealthStatus.from_dict(status_dict))
                except Exception as e:
                    logger.warning(f"Failed to parse consumer health for {key}: {e}")

            return consumers
        except Exception as e:
            logger.warning(f"Failed to get consumer health statuses: {e}")
            return []


def get_consumer_health_summary(
    consumers: list[ConsumerHealthStatus],
) -> Dict[str, Any]:
    """
    Get a summary of consumer health across all instances.

    Args:
        consumers: List of consumer health statuses

    Returns:
        Summary dictionary with overall status and instance details
    """
    if not consumers:
        return {
            "status": "no_consumers",
            "message": "No active consumers registered",
            "instances": [],
        }

    now = datetime.utcnow()
    active_consumers = []
    stale_consumers = []
    error_consumers = []

    for consumer in consumers:
        # Check if heartbeat is stale
        if consumer.last_heartbeat:
            time_since_heartbeat = (now - consumer.last_heartbeat).total_seconds()
            is_stale = time_since_heartbeat > ConsumerHealthTracker.HEALTH_TTL_SECONDS
        else:
            is_stale = True

        if is_stale:
            stale_consumers.append(consumer)
        elif consumer.status == "error":
            error_consumers.append(consumer)
        elif consumer.status in ("running", "starting"):
            active_consumers.append(consumer)
        else:
            stale_consumers.append(consumer)

    # Determine overall status
    if error_consumers:
        overall_status = "unhealthy"
    elif stale_consumers and not active_consumers:
        overall_status = "unhealthy"
    elif stale_consumers:
        overall_status = "degraded"
    elif active_consumers:
        overall_status = "healthy"
    else:
        overall_status = "unknown"

    return {
        "status": overall_status,
        "active_count": len(active_consumers),
        "stale_count": len(stale_consumers),
        "error_count": len(error_consumers),
        "total_events_processed": sum(c.events_processed for c in consumers),
        "total_events_failed": sum(c.events_failed for c in consumers),
        "instances": [c.to_dict() for c in consumers],
    }
