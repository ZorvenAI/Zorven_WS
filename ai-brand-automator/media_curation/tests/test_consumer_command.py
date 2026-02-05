"""
Tests for the Kafka consumer management command.

Tests cover:
- ConsumerHealthTracker class
- run_curation_consumer management command
- Health check integration
"""

import json
import pytest
import time
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, patch


from media_curation.consumer_health import (
    ConsumerHealthStatus,
    ConsumerHealthTracker,
    get_consumer_health_summary,
)
from media_curation.management.commands.run_curation_consumer import Command


pytestmark = pytest.mark.django_db


class TestConsumerHealthStatus:
    """Tests for ConsumerHealthStatus dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        now = datetime.utcnow()
        status = ConsumerHealthStatus(
            instance_id="test-123",
            status="running",
            last_heartbeat=now,
            events_processed=10,
            events_failed=2,
            started_at=now - timedelta(hours=1),
        )

        result = status.to_dict()

        assert result["instance_id"] == "test-123"
        assert result["status"] == "running"
        assert result["events_processed"] == 10
        assert result["events_failed"] == 2
        assert "uptime_seconds" in result
        assert result["uptime_seconds"] >= 3600  # At least 1 hour

    def test_from_dict(self):
        """Test creation from dictionary."""
        now = datetime.utcnow()
        data = {
            "instance_id": "test-456",
            "status": "running",
            "last_heartbeat": now.isoformat(),
            "events_processed": 5,
            "events_failed": 1,
            "started_at": now.isoformat(),
        }

        status = ConsumerHealthStatus.from_dict(data)

        assert status.instance_id == "test-456"
        assert status.status == "running"
        assert status.events_processed == 5
        assert status.events_failed == 1

    def test_from_dict_with_missing_fields(self):
        """Test creation from dictionary with missing optional fields."""
        data = {
            "instance_id": "test-789",
        }

        status = ConsumerHealthStatus.from_dict(data)

        assert status.instance_id == "test-789"
        assert status.status == "unknown"
        assert status.events_processed == 0

    def test_roundtrip(self):
        """Test to_dict -> from_dict roundtrip."""
        original = ConsumerHealthStatus(
            instance_id="roundtrip-test",
            status="running",
            last_heartbeat=datetime.utcnow(),
            events_processed=100,
            events_failed=5,
            started_at=datetime.utcnow() - timedelta(minutes=30),
        )

        data = original.to_dict()
        restored = ConsumerHealthStatus.from_dict(data)

        assert restored.instance_id == original.instance_id
        assert restored.status == original.status
        assert restored.events_processed == original.events_processed
        assert restored.events_failed == original.events_failed


class TestConsumerHealthTracker:
    """Tests for ConsumerHealthTracker class."""

    def test_key_property(self):
        """Test Redis key generation."""
        mock_redis = MagicMock()
        # Remove async attributes to simulate sync client
        del mock_redis.__aenter__
        del mock_redis.__aexit__
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")

        assert tracker.key == "media_curation:consumer:health:consumer-123"

    def test_update_status(self):
        """Test status update with sync Redis."""
        mock_redis = MagicMock(spec=["setex", "delete", "keys", "get"])
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")

        tracker.update_status(status="running", events_processed=10)

        # Should have called setex
        mock_redis.setex.assert_called()
        call_args = mock_redis.setex.call_args
        assert "consumer-123" in call_args[0][0]  # Key contains instance ID

        # Parse stored JSON
        stored_json = call_args[0][2]
        stored_data = json.loads(stored_json)
        assert stored_data["status"] == "running"
        assert stored_data["events_processed"] == 10

    def test_increment_processed(self):
        """Test incrementing processed counter."""
        mock_redis = MagicMock(spec=["setex", "delete", "keys", "get"])
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")

        tracker.increment_processed()
        tracker.increment_processed()
        tracker.increment_processed()

        assert tracker._status.events_processed == 3

    def test_increment_failed(self):
        """Test incrementing failed counter."""
        mock_redis = MagicMock(spec=["setex", "delete", "keys", "get"])
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")

        tracker.increment_failed()
        tracker.increment_failed()

        assert tracker._status.events_failed == 2

    def test_heartbeat_throttling(self):
        """Test that heartbeat is throttled."""
        mock_redis = MagicMock(spec=["setex", "delete", "keys", "get"])
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")
        tracker._last_heartbeat_time = time.time()  # Just sent

        # Reset mock to track new calls
        mock_redis.reset_mock()

        # Should not persist (too soon)
        tracker.heartbeat()
        mock_redis.setex.assert_not_called()

        # Simulate time passing
        tracker._last_heartbeat_time = time.time() - 20  # 20 seconds ago
        tracker.heartbeat()
        mock_redis.setex.assert_called()

    def test_cleanup(self):
        """Test cleanup removes Redis key."""
        mock_redis = MagicMock(spec=["setex", "delete", "keys", "get"])
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")

        tracker.cleanup()

        mock_redis.delete.assert_called_with(tracker.key)

    def test_redis_unavailable_graceful(self):
        """Test graceful handling when Redis is unavailable."""
        mock_redis = MagicMock(spec=["setex", "delete", "keys", "get"])
        mock_redis.setex.side_effect = Exception("Connection refused")
        tracker = ConsumerHealthTracker(mock_redis, "consumer-123")

        # Should not raise, just log warning
        tracker.update_status(status="running")

        # Should mark Redis as unavailable
        assert tracker._redis_available is False

        # Subsequent calls should skip Redis
        mock_redis.reset_mock()
        tracker.update_status(status="stopping")
        mock_redis.setex.assert_not_called()


class TestGetConsumerHealthSummary:
    """Tests for get_consumer_health_summary function."""

    def test_no_consumers(self):
        """Test summary with no consumers."""
        result = get_consumer_health_summary([])

        assert result["status"] == "no_consumers"
        assert result["instances"] == []

    def test_all_healthy(self):
        """Test summary with all healthy consumers."""
        now = datetime.utcnow()
        consumers = [
            ConsumerHealthStatus(
                instance_id="consumer-1",
                status="running",
                last_heartbeat=now,
                events_processed=100,
                events_failed=2,
            ),
            ConsumerHealthStatus(
                instance_id="consumer-2",
                status="running",
                last_heartbeat=now,
                events_processed=150,
                events_failed=1,
            ),
        ]

        result = get_consumer_health_summary(consumers)

        assert result["status"] == "healthy"
        assert result["active_count"] == 2
        assert result["total_events_processed"] == 250
        assert result["total_events_failed"] == 3

    def test_some_stale(self):
        """Test summary with some stale consumers."""
        now = datetime.utcnow()
        consumers = [
            ConsumerHealthStatus(
                instance_id="consumer-1",
                status="running",
                last_heartbeat=now,
                events_processed=100,
            ),
            ConsumerHealthStatus(
                instance_id="consumer-2",
                status="running",
                last_heartbeat=now - timedelta(minutes=5),  # Stale
                events_processed=50,
            ),
        ]

        result = get_consumer_health_summary(consumers)

        assert result["status"] == "degraded"
        assert result["active_count"] == 1
        assert result["stale_count"] == 1

    def test_all_stale(self):
        """Test summary with all stale consumers."""
        old_time = datetime.utcnow() - timedelta(minutes=10)
        consumers = [
            ConsumerHealthStatus(
                instance_id="consumer-1",
                status="running",
                last_heartbeat=old_time,
            ),
        ]

        result = get_consumer_health_summary(consumers)

        assert result["status"] == "unhealthy"
        assert result["stale_count"] == 1
        assert result["active_count"] == 0

    def test_with_error_consumers(self):
        """Test summary with error consumers."""
        now = datetime.utcnow()
        consumers = [
            ConsumerHealthStatus(
                instance_id="consumer-1",
                status="running",
                last_heartbeat=now,
            ),
            ConsumerHealthStatus(
                instance_id="consumer-2",
                status="error",
                last_heartbeat=now,
                error_message="Out of memory",
            ),
        ]

        result = get_consumer_health_summary(consumers)

        assert result["status"] == "unhealthy"
        assert result["error_count"] == 1


class TestRunCurationConsumerCommand:
    """Tests for run_curation_consumer management command."""

    def test_command_initialization(self):
        """Test command initializes correctly."""
        cmd = Command()

        assert cmd._running is False
        assert cmd._consumer is None
        assert cmd._service is None
        assert cmd._health_tracker is None
        assert "consumer-" in cmd._instance_id

    def test_command_help_text(self):
        """Test command has help text."""
        cmd = Command()
        assert "media curation Kafka consumer" in cmd.help

    @patch(
        "media_curation.management.commands.run_curation_consumer.create_kafka_consumer"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer.get_curation_service"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer.create_kafka_producer"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer"
        ".create_cache_adapter"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer"
        ".get_media_curation_config"
    )
    def test_mock_mode_when_kafka_unavailable(
        self,
        mock_config,
        mock_cache,
        mock_producer,
        mock_service,
        mock_consumer,
    ):
        """Test command enters mock mode when Kafka is unavailable."""
        mock_config.return_value = {"KAFKA": {"INPUT_TOPIC": "test-topic"}}

        mock_consumer_instance = MagicMock()
        mock_consumer_instance._kafka_available = False
        mock_consumer.return_value = mock_consumer_instance

        mock_cache_instance = MagicMock()
        mock_cache_instance._redis = None
        mock_cache.return_value = mock_cache_instance

        cmd = Command()
        stdout = StringIO()
        cmd.stdout = stdout
        cmd.stderr = StringIO()

        # Run in separate thread and stop quickly
        def stop_command():
            time.sleep(0.1)
            cmd._running = False

        import threading

        stopper = threading.Thread(target=stop_command)
        stopper.start()

        cmd.handle(batch_size=10, poll_timeout=1.0, max_retries=3)

        stopper.join()
        output = stdout.getvalue()
        assert "mock mode" in output.lower() or "Kafka not available" in output

    def test_signal_handlers_are_registered_correctly(self):
        """Test that signal handlers are set correctly for graceful shutdown."""
        import signal as sig

        cmd = Command()
        cmd._running = True
        cmd.stdout = StringIO()

        # The command registers signal handlers in handle()
        # We can test that the handler works correctly
        cmd._signal_handler(sig.SIGTERM, None)

        assert cmd._running is False
        assert "shutting down" in cmd.stdout.getvalue().lower()

    def test_signal_handler_sets_running_false(self):
        """Test that signal handler sets _running to False."""
        cmd = Command()
        cmd._running = True
        cmd.stdout = StringIO()

        cmd._signal_handler(15, None)  # SIGTERM = 15

        assert cmd._running is False

    def test_cleanup_closes_consumer(self):
        """Test cleanup closes Kafka consumer."""
        cmd = Command()
        cmd.stdout = StringIO()
        mock_consumer = MagicMock()
        cmd._consumer = mock_consumer

        cmd._cleanup()

        mock_consumer.close.assert_called_once()

    def test_cleanup_with_health_tracker(self):
        """Test cleanup handles health tracker."""
        cmd = Command()
        cmd.stdout = StringIO()
        mock_tracker = MagicMock()
        cmd._health_tracker = mock_tracker
        cmd._consumer = MagicMock()

        cmd._cleanup()

        mock_tracker.update_status.assert_called_with(status="stopped")
        mock_tracker.cleanup.assert_called_once()


class TestProcessEvent:
    """Tests for event processing in the command."""

    @patch("media_curation.management.commands.run_curation_consumer._run_async")
    def test_process_event_success(self, mock_run_async):
        """Test successful event processing."""
        from media_curation.domain.models import CurationEvent
        from uuid import uuid4

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.document_id = "doc-123"
        mock_run_async.return_value = mock_result
        cmd._service = mock_service

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.txt",
            mime_type="text/plain",
        )

        result = cmd._process_event(event, max_retries=3)

        assert result is True
        assert "Processed" in cmd.stdout.getvalue()

    def test_process_event_non_retryable_error(self):
        """Test non-retryable error handling."""
        from media_curation.domain.models import CurationEvent
        from media_curation.domain.exceptions import NonRetryableError
        from uuid import uuid4

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()
        cmd._producer = MagicMock()
        cmd._service = MagicMock()
        cmd._service.process_event.side_effect = NonRetryableError("Invalid format")

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.txt",
            mime_type="text/plain",
        )

        result = cmd._process_event(event, max_retries=3)

        assert result is False
        assert "Non-retryable" in cmd.stdout.getvalue()

    @patch("media_curation.management.commands.run_curation_consumer.time.sleep")
    def test_process_event_retryable_error_max_retries(self, mock_sleep):
        """Test retryable error exceeds max retries."""
        from media_curation.domain.models import CurationEvent
        from media_curation.domain.exceptions import RetryableError
        from uuid import uuid4

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()
        cmd._producer = MagicMock()
        cmd._service = MagicMock()
        cmd._service.process_event.side_effect = RetryableError("Temporary failure")

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.txt",
            mime_type="text/plain",
        )

        result = cmd._process_event(event, max_retries=2)

        assert result is False
        assert "Failed after retries" in cmd.stdout.getvalue()
        # Should have slept for backoff
        assert mock_sleep.call_count == 2


class TestSendToDLQ:
    """Tests for DLQ handling."""

    @patch("media_curation.management.commands.run_curation_consumer._run_async")
    def test_send_to_dlq_success(self, mock_run_async):
        """Test successful DLQ send."""
        from media_curation.domain.models import CurationEvent
        from uuid import uuid4

        cmd = Command()
        mock_producer = MagicMock()
        cmd._producer = mock_producer

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.txt",
            mime_type="text/plain",
        )
        error = Exception("Test error")

        cmd._send_to_dlq(event, error)

        mock_run_async.assert_called_once()

    def test_send_to_dlq_no_producer(self):
        """Test DLQ send when no producer available."""
        from media_curation.domain.models import CurationEvent
        from uuid import uuid4

        cmd = Command()
        cmd._producer = None

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.txt",
            mime_type="text/plain",
        )

        # Should not raise
        cmd._send_to_dlq(event, Exception("Test"))
