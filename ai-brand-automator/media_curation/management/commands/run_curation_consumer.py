"""
Kafka Consumer Management Command for Media Curation.

Runs a Kafka consumer that listens to curation-needed-topic
and processes incoming events.
"""

import asyncio
import logging
import os
import signal
import time
import uuid

from django.core.management.base import BaseCommand, CommandError

from media_curation.factory import (
    get_media_curation_config,
    get_curation_service,
    create_kafka_consumer,
    create_kafka_producer,
    create_cache_adapter,
)
from media_curation.domain.models import CurationEvent
from media_curation.domain.exceptions import (
    RetryableError,
    NonRetryableError,
)
from media_curation.consumer_health import ConsumerHealthTracker


logger = logging.getLogger(__name__)


def _update_asset_status(file_id: str, status: str, error_msg: str = "") -> bool:
    """Update BrandAsset pipeline_status after curation.

    Args:
        file_id: The file/asset ID (can be UUID string or int)
        status: The new pipeline status (curated, failed)
        error_msg: Error message if status is failed

    Returns:
        True if update succeeded, False otherwise
    """
    from django.db import close_old_connections
    from onboarding.models import BrandAsset

    for attempt in range(2):
        try:
            if attempt > 0:
                close_old_connections()

            # Try to find asset by ID (could be integer or UUID)
            try:
                asset_id = int(file_id)
                asset = BrandAsset.objects.filter(id=asset_id).first()
            except (ValueError, TypeError):
                # file_id might be a UUID - try matching by pipeline_trace_id
                try:
                    trace_uuid = uuid.UUID(file_id)
                    asset = BrandAsset.objects.filter(
                        pipeline_trace_id=trace_uuid
                    ).first()
                except (ValueError, TypeError):
                    asset = None

            if asset:
                asset.pipeline_status = status
                if error_msg:
                    asset.pipeline_error = error_msg
                asset.save(update_fields=["pipeline_status", "pipeline_error"])
                logger.info(
                    "Updated BrandAsset %s pipeline_status to %s",
                    asset.id,
                    status,
                )
                return True
            else:
                logger.warning("BrandAsset not found for file_id: %s", file_id)
                return False

        except Exception:
            if attempt == 0:
                logger.warning(
                    "DB error updating BrandAsset (will retry): %s",
                    file_id,
                    exc_info=True,
                )
                continue
            logger.exception("Failed to update BrandAsset status after retry")
            return False

    return False


def _run_async(coro):
    """Helper to run async coroutines in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class Command(BaseCommand):
    """
    Django management command to run the curation Kafka consumer.

    Usage:
        python manage.py run_curation_consumer
        python manage.py run_curation_consumer --batch-size 20 --poll-timeout 2.0
    """

    help = "Run the media curation Kafka consumer"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._running = False
        self._consumer = None
        self._service = None
        self._producer = None
        self._health_tracker = None
        self._instance_id = f"consumer-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--batch-size",
            type=int,
            default=10,
            help="Number of messages to consume per batch (default: 10)",
        )
        parser.add_argument(
            "--poll-timeout",
            type=float,
            default=1.0,
            help="Kafka poll timeout in seconds (default: 1.0)",
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=3,
            help="Maximum retries for failed events (default: 3)",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        batch_size = options["batch_size"]
        poll_timeout = options["poll_timeout"]
        max_retries = options["max_retries"]

        self.stdout.write("Starting media curation consumer...")
        self.stdout.write(f"Instance ID: {self._instance_id}")
        self.stdout.write(f"Batch size: {batch_size}, Poll timeout: {poll_timeout}s")

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            # Initialize components
            config = get_media_curation_config()
            kafka_config = config.get("KAFKA", {})

            # Initialize health tracker with Redis
            try:
                cache_adapter = create_cache_adapter()
                if hasattr(cache_adapter, "_redis") and cache_adapter._redis:
                    self._health_tracker = ConsumerHealthTracker(
                        redis_client=cache_adapter._redis,
                        instance_id=self._instance_id,
                    )
                    self._health_tracker.update_status(status="starting")
                    self.stdout.write("Health tracking enabled via Redis")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "Redis not available - health tracking disabled"
                        )
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f"Could not initialize health tracker: {e}")
                )

            self.stdout.write(
                f"Connecting to Kafka topic: {kafka_config.get('INPUT_TOPIC')}"
            )

            # Create consumer and service
            self._consumer = create_kafka_consumer(config)
            self._service = get_curation_service(config)
            self._producer = create_kafka_producer(config)

            # Check if Kafka is available
            if not getattr(self._consumer, "_kafka_available", False):
                self.stdout.write(
                    self.style.WARNING(
                        "Kafka not available - running in mock mode. "
                        "Consumer will wait for signals."
                    )
                )
                if self._health_tracker:
                    self._health_tracker.update_status(
                        status="running", error_message="Kafka unavailable - mock mode"
                    )
                self._running = True
                while self._running:
                    if self._health_tracker:
                        self._health_tracker.heartbeat()
                    time.sleep(1)
                return

            # Subscribe to topic
            self._consumer.subscribe()
            self.stdout.write(
                self.style.SUCCESS(f"Subscribed to: {kafka_config.get('INPUT_TOPIC')}")
            )

            # Update health status to running
            if self._health_tracker:
                self._health_tracker.update_status(status="running")

            # Main consumer loop
            self._running = True
            events_processed = 0
            events_failed = 0

            while self._running:
                try:
                    # Send periodic heartbeat
                    if self._health_tracker:
                        self._health_tracker.heartbeat()

                    events = _run_async(
                        self._consumer.consume_batch(
                            max_messages=batch_size,
                            timeout=poll_timeout,
                        )
                    )

                    if self._health_tracker and events:
                        self._health_tracker.update_status(
                            current_batch_size=len(events)
                        )

                    for event in events:
                        success = self._process_event(event, max_retries)
                        if success:
                            events_processed += 1
                            if self._health_tracker:
                                self._health_tracker.increment_processed()
                        else:
                            events_failed += 1
                            if self._health_tracker:
                                self._health_tracker.increment_failed()

                    if events:
                        self._consumer.commit()
                        if self._health_tracker:
                            self._health_tracker.update_status(
                                events_processed=events_processed,
                                events_failed=events_failed,
                                current_batch_size=0,
                            )
                        self.stdout.write(
                            f"Processed batch of {len(events)} events "
                            f"(total: {events_processed}, failed: {events_failed})"
                        )

                except Exception as e:
                    logger.exception("Consumer error")
                    self.stderr.write(f"Error: {e}")
                    if self._health_tracker:
                        self._health_tracker.update_status(error_message=str(e))
                    time.sleep(1)  # Brief pause before retrying

        except KeyboardInterrupt:
            self.stdout.write("\nReceived interrupt signal")
        except Exception as e:
            if self._health_tracker:
                self._health_tracker.update_status(status="error", error_message=str(e))
            raise CommandError(f"Consumer failed: {e}")
        finally:
            self._cleanup()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.stdout.write(f"\nReceived signal {signum}, shutting down gracefully...")
        if self._health_tracker:
            self._health_tracker.update_status(status="stopping")
        self._running = False

    def _process_event(self, event: CurationEvent, max_retries: int) -> bool:
        """
        Process a single curation event with retry logic.

        Args:
            event: The curation event to process
            max_retries: Maximum retry attempts

        Returns:
            True if processing succeeded, False otherwise
        """
        retry_count = 0
        backoff = 1.0

        # Get asset_id from metadata for status updates
        asset_id = None
        if event.metadata and "asset_id" in event.metadata:
            asset_id = str(event.metadata["asset_id"])

        while retry_count <= max_retries:
            try:
                # process_event is synchronous, call it directly
                result = self._service.process_event(event)
                doc_id = result.document_id if result else "N/A"

                # Update BrandAsset status to curated (use asset_id from metadata)
                if asset_id:
                    _update_asset_status(asset_id, "curated")
                else:
                    logger.warning(
                        f"No asset_id in metadata for event {event.event_id}"
                    )

                self.stdout.write(
                    self.style.SUCCESS(f"✓ Processed: {event.event_id} -> {doc_id}")
                )
                return True

            except RetryableError as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(
                        "Max retries exceeded",
                        extra={
                            "event_id": str(event.event_id),
                            "trace_id": str(event.trace_id),
                        },
                    )
                    # Update BrandAsset status to failed
                    if asset_id:
                        _update_asset_status(asset_id, "failed", str(e))

                    self._send_to_dlq(event, e)
                    self.stdout.write(
                        self.style.ERROR(f"✗ Failed after retries: {event.event_id}")
                    )
                    return False

                logger.warning(
                    f"Retrying event after {backoff}s",
                    extra={
                        "event_id": str(event.event_id),
                        "retry_count": retry_count,
                    },
                )
                time.sleep(backoff)
                backoff *= 2

            except NonRetryableError as e:
                logger.error(
                    "Non-retryable error",
                    extra={
                        "event_id": str(event.event_id),
                        "error": str(e),
                    },
                )
                # Update BrandAsset status to failed
                if asset_id:
                    _update_asset_status(asset_id, "failed", str(e))

                self._send_to_dlq(event, e)
                self.stdout.write(
                    self.style.ERROR(f"✗ Non-retryable: {event.event_id} - {e}")
                )
                return False

            except Exception as e:
                logger.exception("Unexpected error processing event")
                # Update BrandAsset status to failed
                if asset_id:
                    _update_asset_status(asset_id, "failed", str(e))

                self._send_to_dlq(event, e)
                self.stdout.write(
                    self.style.ERROR(f"✗ Unexpected error: {event.event_id}")
                )
                return False

        # Should not reach here, but return False for safety
        return False

    def _send_to_dlq(self, event: CurationEvent, error: Exception) -> None:
        """Send failed event to dead letter queue."""
        try:
            if self._producer:
                _run_async(self._producer.publish_to_dlq(event, error))
                logger.info(
                    "Event sent to DLQ",
                    extra={
                        "event_id": str(event.event_id),
                        "trace_id": str(event.trace_id),
                    },
                )
            else:
                logger.warning("No producer available to send to DLQ")
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")

    def _cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        self.stdout.write("Cleaning up...")

        # Update health status to stopped
        if self._health_tracker:
            try:
                self._health_tracker.update_status(status="stopped")
                self._health_tracker.cleanup()
                logger.info("Consumer health tracking cleaned up")
            except Exception as e:
                logger.error(f"Error cleaning up health tracker: {e}")

        if self._consumer:
            try:
                self._consumer.close()
                logger.info("Kafka consumer closed")
            except Exception as e:
                logger.error(f"Error closing consumer: {e}")

        self.stdout.write("Cleanup complete")
