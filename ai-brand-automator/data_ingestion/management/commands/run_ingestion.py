"""
Django management command to run the data ingestion consumer.

Usage:
    python manage.py run_ingestion
    python manage.py run_ingestion --batch-size 100 --poll-timeout 2.0
"""

import signal
import logging
import uuid

from django.core.management.base import BaseCommand, CommandError

from data_ingestion.factory import (
    IngestionServiceContainer,
    create_kafka_consumer,
    get_data_ingestion_config,
)
from data_ingestion.domain.models import IngestionEvent
from data_ingestion.domain.exceptions import (
    NonRetryableError,
    RetryableError,
)


logger = logging.getLogger(__name__)


def _update_asset_status(file_id: str, status: str, error_msg: str = "") -> bool:
    """Update BrandAsset pipeline_status after ingestion.

    Args:
        file_id: The asset ID (integer string or UUID string)
        status: The new pipeline status (ingested, failed)
        error_msg: Error message if status is failed

    Returns:
        True if update succeeded, False otherwise
    """
    try:
        from onboarding.models import BrandAsset

        try:
            asset_id = int(file_id)
            asset = BrandAsset.objects.filter(id=asset_id).first()
        except (ValueError, TypeError):
            try:
                trace_uuid = uuid.UUID(file_id)
                asset = BrandAsset.objects.filter(pipeline_trace_id=trace_uuid).first()
            except (ValueError, TypeError):
                asset = None

        if asset:
            asset.pipeline_status = status
            update_fields = ["pipeline_status"]
            if error_msg:
                asset.pipeline_error = error_msg
                update_fields.append("pipeline_error")
            asset.save(update_fields=update_fields)
            logger.info(
                "Updated BrandAsset %s pipeline_status to %s",
                asset.id,
                status,
            )
            return True
        else:
            logger.warning("BrandAsset not found for file_id: %s", file_id)
            return False

    except Exception as e:
        logger.error("Failed to update BrandAsset status: %s", e)
        return False


def _get_input_topic() -> str:
    """Get the input topic from config, supporting both nested and flat keys."""
    config = get_data_ingestion_config()
    kafka_config = config.get("KAFKA", {})
    return kafka_config.get(
        "INPUT_TOPIC",
        config.get("KAFKA_INPUT_TOPIC", "raw-ingestion-topic"),
    )


class Command(BaseCommand):
    """Django management command to run the ingestion consumer."""

    help = "Run the data ingestion Kafka consumer"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._running = True
        self._consumer = None
        self._service = None

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1,
            help="Number of messages to process per batch (default: 1)",
        )
        parser.add_argument(
            "--poll-timeout",
            type=float,
            default=1.0,
            help="Kafka poll timeout in seconds (default: 1.0)",
        )
        parser.add_argument(
            "--max-messages",
            type=int,
            default=None,
            help="Maximum messages to process before exiting (default: unlimited)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Log events without processing them",
        )

    def handle(self, *args, **options):
        """Main entry point for the command."""
        batch_size = options["batch_size"]
        poll_timeout = options["poll_timeout"]
        max_messages = options["max_messages"]
        dry_run = options["dry_run"]

        self.stdout.write(self.style.SUCCESS("Starting data ingestion consumer..."))

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            # Get service and consumer from container
            self._service = IngestionServiceContainer.get_service()
            self._consumer = create_kafka_consumer()
            self._consumer.subscribe()

            config = get_data_ingestion_config()
            kafka_config = config.get("KAFKA", {})

            self.stdout.write(
                f"Consumer started. Listening to: {kafka_config.get('INPUT_TOPIC', 'raw-ingestion-topic')}"
            )
            self.stdout.write(
                f"Batch size: {batch_size}, Poll timeout: {poll_timeout}s"
            )

            if dry_run:
                self.stdout.write(
                    self.style.WARNING("DRY RUN MODE - events will not be processed")
                )

            processed_count = 0

            while self._running:
                # Check max messages limit
                if max_messages and processed_count >= max_messages:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Reached max messages limit ({max_messages})"
                        )
                    )
                    break

                # Consume batch
                if batch_size == 1:
                    event = self._consumer.consume_one(timeout=poll_timeout)
                    events = [event] if event else []
                else:
                    events = self._consumer.consume_batch(
                        max_messages=batch_size,
                        timeout=poll_timeout,
                    )

                if not events:
                    continue

                # Process events
                for event in events:
                    if dry_run:
                        self._log_event(event)
                    else:
                        self._process_event(event)

                    processed_count += 1

                    if max_messages and processed_count >= max_messages:
                        break

                # Commit after batch
                self._consumer.commit()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Consumer stopped. Processed {processed_count} events."
                )
            )

        except Exception as e:
            logger.exception("Consumer error")
            raise CommandError(f"Consumer failed: {e}")

        finally:
            self._cleanup()

    def _process_event(self, event: IngestionEvent) -> None:
        """Process a single ingestion event."""
        try:
            result = self._service.process_event_with_retry(event)

            if result:
                # Update BrandAsset pipeline_status to "ingested"
                asset_id = (event.metadata or {}).get("asset_id")
                if asset_id:
                    _update_asset_status(str(asset_id), "ingested")

                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Processed: {event.event_id} -> {result.destination_path}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"⊘ Skipped duplicate: {event.event_id}")
                )

        except NonRetryableError as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Failed (non-retryable): {event.event_id} - {e}")
            )
            asset_id = (event.metadata or {}).get("asset_id")
            if asset_id:
                _update_asset_status(str(asset_id), "failed", str(e))
            # Send to DLQ
            self._service.send_to_dlq(
                original_event=event.model_dump(mode="json"),
                error=e,
                source_topic=_get_input_topic(),
            )

        except RetryableError as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Failed after retries: {event.event_id} - {e}")
            )
            asset_id = (event.metadata or {}).get("asset_id")
            if asset_id:
                _update_asset_status(str(asset_id), "failed", str(e))
            # Send to DLQ after max retries
            self._service.send_to_dlq(
                original_event=event.model_dump(mode="json"),
                error=e,
                source_topic=_get_input_topic(),
            )

    def _log_event(self, event: IngestionEvent) -> None:
        """Log event details in dry-run mode."""
        self.stdout.write(
            f"[DRY RUN] Event: {event.event_id}\n"
            f"  tenant_id: {event.tenant_id}\n"
            f"  file_path: {event.file_path}\n"
            f"  timestamp: {event.timestamp}\n"
            f"  source: {event.source.value if event.source else 'N/A'}"
        )

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = signal.Signals(signum).name
        self.stdout.write(f"\nReceived {signal_name}, shutting down gracefully...")
        self._running = False

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._consumer:
            try:
                self._consumer.close()
            except Exception as e:
                logger.warning(f"Error closing consumer: {e}")

        # Flush producer
        if self._service and hasattr(self._service, "producer"):
            try:
                self._service.producer.flush()
            except Exception as e:
                logger.warning(f"Error flushing producer: {e}")

        IngestionServiceContainer.reset()
        self.stdout.write("Cleanup complete")
