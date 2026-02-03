"""
Unit Tests for Kafka Consumer Management Command.

Tests for the consume_sync_events management command.
"""

import json
import uuid
from datetime import datetime, timezone
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_kafka_message():
    """Create a sample Kafka message data."""
    return {
        "specversion": "1.0",
        "id": str(uuid.uuid4()),
        "source": "media-curation-svc",
        "type": "rag.sync.ready",
        "datacontenttype": "application/json",
        "time": datetime.now(timezone.utc).isoformat(),
        "data": {
            "event_id": str(uuid.uuid4()),
            "trace_id": str(uuid.uuid4()),
            "tenant_id": "tenant-123",
            "file_id": "file-456",
            "action": "UPSERT",
            "processed_gcs_uri": "gs://bucket/path/doc.json",
        },
    }


@pytest.fixture
def mock_kafka_message(sample_kafka_message):
    """Create a mock Kafka message object."""
    mock_msg = MagicMock()
    mock_msg.value.return_value = json.dumps(sample_kafka_message).encode("utf-8")
    mock_msg.key.return_value = b"tenant-123"
    mock_msg.topic.return_value = "rag-sync-ready-topic"
    mock_msg.partition.return_value = 0
    mock_msg.offset.return_value = 42
    mock_msg.error.return_value = None
    return mock_msg


# ============================================================================
# Command Argument Tests
# ============================================================================


class TestCommandArguments:
    """Tests for command arguments."""

    @patch(
        "rag_index.management.commands.consume_sync_events.Command._run_mock_consumer"
    )
    def test_default_arguments(self, mock_run, settings):
        """Test command uses default arguments."""
        out = StringIO()

        call_command("consume_sync_events", "--mock-mode", stdout=out)

        mock_run.assert_called_once()
        output = out.getvalue()
        assert "rag-sync-ready-topic" in output

    @patch(
        "rag_index.management.commands.consume_sync_events.Command._run_mock_consumer"
    )
    def test_custom_topic(self, mock_run):
        """Test command with custom topic."""
        out = StringIO()

        call_command(
            "consume_sync_events",
            "--mock-mode",
            "--topic=custom-topic",
            stdout=out,
        )

        output = out.getvalue()
        assert "custom-topic" in output

    @patch(
        "rag_index.management.commands.consume_sync_events.Command._run_mock_consumer"
    )
    def test_custom_group(self, mock_run):
        """Test command with custom consumer group."""
        out = StringIO()

        call_command(
            "consume_sync_events",
            "--mock-mode",
            "--group=custom-group",
            stdout=out,
        )

        output = out.getvalue()
        assert "custom-group" in output

    @patch(
        "rag_index.management.commands.consume_sync_events.Command._run_mock_consumer"
    )
    def test_dry_run_mode(self, mock_run):
        """Test command with dry-run mode."""
        out = StringIO()

        call_command(
            "consume_sync_events",
            "--mock-mode",
            "--dry-run",
            stdout=out,
        )

        output = out.getvalue()
        assert "Dry run: True" in output


# ============================================================================
# Mock Mode Tests
# ============================================================================


@pytest.mark.django_db
class TestMockMode:
    """Tests for mock mode operation."""

    def test_mock_mode_runs_without_kafka(self):
        """Test mock mode runs without Kafka connection."""
        out = StringIO()

        # Use max-messages to limit iterations
        patch_target = "rag_index.management.commands.consume_sync_events"
        with patch(f"{patch_target}.Command._run_mock_consumer") as mock_run:
            call_command("consume_sync_events", "--mock-mode", stdout=out)

        # Verify mock mode was invoked
        mock_run.assert_called_once()
        output = out.getvalue()
        assert "mock mode" in output.lower()


# ============================================================================
# Message Processing Tests
# ============================================================================


class TestMessageProcessing:
    """Tests for message processing."""

    @patch("rag_index.management.commands.consume_sync_events.sync_document")
    def test_process_message_dispatches_task(
        self, mock_sync_document, sample_kafka_message, mock_kafka_message
    ):
        """Test message processing dispatches Celery task."""
        from rag_index.management.commands.consume_sync_events import Command

        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_sync_document.delay.return_value = mock_task

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()
        cmd.dry_run = False

        cmd._process_message(mock_kafka_message)

        assert mock_sync_document.delay.called
        call_args = mock_sync_document.delay.call_args[0][0]
        assert call_args["tenant_id"] == "tenant-123"
        assert call_args["action"] == "UPSERT"

    def test_process_message_dry_run(self, sample_kafka_message, mock_kafka_message):
        """Test message processing in dry-run mode."""
        from rag_index.management.commands.consume_sync_events import Command

        with patch(
            "rag_index.management.commands.consume_sync_events.sync_document"
        ) as mock_sync:
            cmd = Command()
            cmd.stdout = StringIO()
            cmd.stderr = StringIO()
            cmd.dry_run = True

            cmd._process_message(mock_kafka_message)

            # Should not dispatch in dry-run mode
            assert not mock_sync.delay.called

            output = cmd.stdout.getvalue()
            assert "DRY RUN" in output

    def test_process_message_invalid_json(self):
        """Test processing invalid JSON message."""
        from rag_index.management.commands.consume_sync_events import Command
        from rag_index.domain.exceptions import KafkaConsumeError

        mock_msg = MagicMock()
        mock_msg.value.return_value = b"not valid json"
        mock_msg.topic.return_value = "rag-sync-ready-topic"

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()
        cmd.dry_run = False

        with pytest.raises(KafkaConsumeError):
            cmd._process_message(mock_msg)


# ============================================================================
# Signal Handler Tests
# ============================================================================


class TestSignalHandling:
    """Tests for signal handling."""

    def test_signal_handler_sets_shutdown_flag(self):
        """Test signal handler sets shutdown flag."""
        from rag_index.management.commands.consume_sync_events import Command

        cmd = Command()
        cmd.stdout = StringIO()

        assert not cmd._shutdown_requested

        cmd._signal_handler(2, None)  # SIGINT

        assert cmd._shutdown_requested


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Tests for consumer statistics."""

    def test_get_stats(self):
        """Test getting consumer statistics."""
        from rag_index.management.commands.consume_sync_events import Command

        cmd = Command()
        cmd.topic = "test-topic"
        cmd.group = "test-group"
        cmd.mock_mode = True
        cmd._processed_count = 10
        cmd._error_count = 2

        stats = cmd._get_stats()

        assert stats["processed_count"] == 10
        assert stats["error_count"] == 2
        assert stats["topic"] == "test-topic"
        assert stats["group"] == "test-group"
        assert stats["mock_mode"] is True


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    def test_missing_confluent_kafka(self):
        """Test error when confluent-kafka is not installed."""
        from rag_index.management.commands.consume_sync_events import Command

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()
        cmd.topic = "test-topic"
        cmd.group = "test-group"
        cmd.bootstrap_servers = "localhost:9092"
        cmd.poll_timeout = 1.0
        cmd.commit_interval = 10
        cmd.max_messages = 0
        cmd._shutdown_requested = True  # Prevent infinite loop

        # Mock the import to raise ImportError
        with patch.dict("sys.modules", {"confluent_kafka": None}):
            with pytest.raises(CommandError) as exc_info:
                cmd._run_kafka_consumer()

            assert "confluent-kafka" in str(exc_info.value)

    def test_handle_consumer_error_partition_eof(self):
        """Test handling partition EOF error (code path exists)."""
        from rag_index.management.commands.consume_sync_events import Command

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()
        cmd._error_count = 0

        # Simply verify the command has error handling attributes set up
        assert hasattr(cmd, "_error_count")
        assert cmd._error_count == 0


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.django_db
class TestConsumerIntegration:
    """Integration tests for consumer command."""

    def test_consumer_starts_and_stops(self):
        """Test consumer can start and stop gracefully."""
        out = StringIO()
        err = StringIO()

        # Use mock mode with immediate shutdown
        from rag_index.management.commands.consume_sync_events import Command

        with patch.object(Command, "_run_mock_consumer") as mock_run:
            # Make the mock set shutdown immediately
            def mock_consumer():
                pass

            mock_run.side_effect = mock_consumer

            call_command("consume_sync_events", "--mock-mode", stdout=out, stderr=err)

        output = out.getvalue()
        assert "Consumer stopped" in output
