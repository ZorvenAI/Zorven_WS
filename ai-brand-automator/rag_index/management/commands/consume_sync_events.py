"""
Kafka Consumer Management Command.

Django management command to run a Kafka consumer that listens
to the rag-sync-ready-topic and processes sync events.

Usage:
    python manage.py consume_sync_events
    python manage.py consume_sync_events --topic custom-topic
    python manage.py consume_sync_events --group custom-group
"""

import json
import logging
import signal
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rag_index.domain.exceptions import (
    KafkaConsumeError,
)
from rag_index.domain.schemas import RagSyncReadyEvent
from rag_index.tasks.sync_tasks import sync_document

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Django management command to consume sync events from Kafka."""

    help = "Consume sync events from Kafka topic and dispatch to Celery workers"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._consumer = None
        self._shutdown_requested = False
        self._processed_count = 0
        self._error_count = 0

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--topic",
            type=str,
            default=getattr(settings, "KAFKA_SYNC_TOPIC", "rag-sync-ready-topic"),
            help="Kafka topic to consume from (default: rag-sync-ready-topic)",
        )
        parser.add_argument(
            "--group",
            type=str,
            default=getattr(settings, "KAFKA_CONSUMER_GROUP", "rag-index-consumers"),
            help="Kafka consumer group ID (default: rag-index-consumers)",
        )
        parser.add_argument(
            "--bootstrap-servers",
            type=str,
            default=getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            help="Kafka bootstrap servers (default: localhost:9092)",
        )
        parser.add_argument(
            "--max-messages",
            type=int,
            default=0,
            help="Maximum messages to process (0 = unlimited)",
        )
        parser.add_argument(
            "--poll-timeout",
            type=float,
            default=1.0,
            help="Poll timeout in seconds (default: 1.0)",
        )
        parser.add_argument(
            "--commit-interval",
            type=int,
            default=10,
            help="Commit offset after N messages (default: 10)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Process messages but don't dispatch to Celery",
        )
        parser.add_argument(
            "--mock-mode",
            action="store_true",
            help="Use mock mode (no real Kafka connection)",
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.topic = options["topic"]
        self.group = options["group"]
        self.bootstrap_servers = options["bootstrap_servers"]
        self.max_messages = options["max_messages"]
        self.poll_timeout = options["poll_timeout"]
        self.commit_interval = options["commit_interval"]
        self.dry_run = options["dry_run"]
        self.mock_mode = options["mock_mode"] or getattr(
            settings, "KAFKA_MOCK_MODE", False
        )

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.stdout.write("Starting Kafka consumer...")
        self.stdout.write(f"  Topic: {self.topic}")
        self.stdout.write(f"  Group: {self.group}")
        self.stdout.write(f"  Bootstrap servers: {self.bootstrap_servers}")
        self.stdout.write(f"  Mock mode: {self.mock_mode}")
        self.stdout.write(f"  Dry run: {self.dry_run}")

        if self.mock_mode:
            self._run_mock_consumer()
        else:
            self._run_kafka_consumer()

        msg = f"Consumer stopped. Processed: {self._processed_count}, "
        msg += f"Errors: {self._error_count}"
        self.stdout.write(self.style.SUCCESS(msg))

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.stdout.write(self.style.WARNING("\nShutdown requested..."))
        self._shutdown_requested = True

    def _run_mock_consumer(self):
        """Run in mock mode without real Kafka connection."""
        self.stdout.write(
            self.style.WARNING("Running in mock mode - no messages to consume")
        )

        # In mock mode, just wait for shutdown
        while not self._shutdown_requested:
            time.sleep(1)
            if self.max_messages and self._processed_count >= self.max_messages:
                break

    def _run_kafka_consumer(self):
        """Run the real Kafka consumer."""
        try:
            from confluent_kafka import Consumer, KafkaException
        except ImportError:
            raise CommandError(
                "confluent-kafka package is not installed. "
                "Install it with: pip install confluent-kafka"
            )

        # Configure consumer
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # We'll commit manually
            "max.poll.interval.ms": 300000,  # 5 minutes
        }

        # Add SASL/SSL config for managed Kafka (Confluent Cloud, etc.)
        sasl_config = getattr(settings, "KAFKA_SASL_CONFIG", {})
        if sasl_config:
            config.update(sasl_config)
            logger.info("Kafka SASL/SSL authentication enabled")

        try:
            self._consumer = Consumer(config)
            self._consumer.subscribe([self.topic])

            self.stdout.write(f"Subscribed to topic: {self.topic}")

            messages_since_commit = 0

            while not self._shutdown_requested:
                # Check max messages limit
                if self.max_messages and self._processed_count >= self.max_messages:
                    self.stdout.write("Max messages limit reached")
                    break

                # Poll for message
                msg = self._consumer.poll(self.poll_timeout)

                if msg is None:
                    continue

                if msg.error():
                    self._handle_consumer_error(msg.error())
                    continue

                # Process the message
                try:
                    self._process_message(msg)
                    self._processed_count += 1
                    messages_since_commit += 1

                    # Commit periodically
                    if messages_since_commit >= self.commit_interval:
                        self._consumer.commit()
                        messages_since_commit = 0

                except Exception as e:
                    self._error_count += 1
                    logger.error(
                        "Failed to process message",
                        extra={"error": str(e), "offset": msg.offset()},
                    )
                    self.stderr.write(
                        self.style.ERROR(f"Error processing message: {e}")
                    )

            # Final commit before shutdown
            if messages_since_commit > 0:
                self._consumer.commit()

        except KafkaException as e:
            raise CommandError(f"Kafka error: {e}")

        finally:
            if self._consumer:
                self._consumer.close()
                self.stdout.write("Consumer closed")

    def _handle_consumer_error(self, error):
        """Handle Kafka consumer errors."""
        from confluent_kafka import KafkaError

        if error.code() == KafkaError._PARTITION_EOF:
            # End of partition, not really an error
            return

        logger.error(f"Kafka consumer error: {error}")
        self.stderr.write(self.style.ERROR(f"Consumer error: {error}"))
        self._error_count += 1

    def _process_message(self, msg):
        """Process a single Kafka message.

        Parses the CloudEvent message and dispatches to Celery.
        """
        try:
            # Parse message value as JSON
            value = json.loads(msg.value().decode("utf-8"))

            logger.debug(
                "Received message",
                extra={
                    "topic": msg.topic(),
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                    "key": msg.key().decode("utf-8") if msg.key() else None,
                },
            )

            # Parse as CloudEvent
            event = RagSyncReadyEvent.from_kafka_message(value)

            # Convert to SyncEvent for task
            sync_event = event.to_sync_event()
            event_dict = sync_event.to_dict()

            if self.dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would dispatch event: {event_dict['event_id']}"
                )
            else:
                # Dispatch to Celery
                task = sync_document.delay(event_dict)
                logger.info(
                    "Dispatched sync task",
                    extra={
                        "event_id": str(sync_event.event_id),
                        "task_id": task.id,
                        "action": sync_event.action.value,
                    },
                )
                self.stdout.write(
                    f"Dispatched event {sync_event.event_id} -> task {task.id}"
                )

        except json.JSONDecodeError as e:
            raise KafkaConsumeError(
                message=f"Invalid JSON in message: {e}",
                topic=msg.topic(),
            )
        except Exception as e:
            raise KafkaConsumeError(
                message=f"Failed to process message: {e}",
                topic=msg.topic(),
            )

    def _get_stats(self) -> dict[str, Any]:
        """Get consumer statistics."""
        return {
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "topic": self.topic,
            "group": self.group,
            "mock_mode": self.mock_mode,
        }
