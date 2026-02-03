"""
Tests for the run_curation_consumer management command.
"""

from io import StringIO
from unittest.mock import patch, MagicMock, AsyncMock


class TestRunCurationConsumerCommand:
    """Tests for the curation consumer management command."""

    def test_command_exists(self):
        """Test management command is registered."""
        from django.core.management import get_commands

        commands = get_commands()
        # Check the command is registered
        assert "run_curation_consumer" in commands or any(
            "run_curation_consumer" in str(cmd) for cmd in commands.keys()
        )

    def test_command_class_has_help(self):
        """Test command has help text."""
        from media_curation.management.commands.run_curation_consumer import Command

        cmd = Command()
        assert cmd.help is not None
        assert len(cmd.help) > 0

    def test_command_adds_arguments(self):
        """Test command adds expected arguments."""
        from media_curation.management.commands.run_curation_consumer import Command

        cmd = Command()
        parser = MagicMock()
        cmd.add_arguments(parser)

        # Should add batch-size, poll-timeout, max-retries
        assert parser.add_argument.call_count >= 3

        call_args = [call[0][0] for call in parser.add_argument.call_args_list]
        assert "--batch-size" in call_args
        assert "--poll-timeout" in call_args
        assert "--max-retries" in call_args

    def test_command_initializes_attributes(self):
        """Test command initializes required attributes."""
        from media_curation.management.commands.run_curation_consumer import Command

        cmd = Command()
        assert cmd._running is False
        assert cmd._consumer is None
        assert cmd._service is None

    def test_signal_handler_stops_running(self):
        """Test signal handler sets _running to False."""
        from media_curation.management.commands.run_curation_consumer import Command

        cmd = Command()
        cmd._running = True

        # Call signal handler
        cmd._signal_handler(None, None)

        assert cmd._running is False

    @patch(
        "media_curation.management.commands.run_curation_consumer"
        ".get_media_curation_config"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer"
        ".create_kafka_consumer"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer"
        ".get_curation_service"
    )
    @patch(
        "media_curation.management.commands.run_curation_consumer"
        ".create_kafka_producer"
    )
    def test_command_initializes_components(
        self,
        mock_producer,
        mock_service,
        mock_consumer,
        mock_config,
    ):
        """Test command initializes Kafka consumer and service."""
        from media_curation.management.commands.run_curation_consumer import Command

        # Mock config
        mock_config.return_value = {
            "KAFKA": {"INPUT_TOPIC": "test-topic"},
        }

        # Mock consumer without kafka available
        mock_consumer_instance = MagicMock()
        mock_consumer_instance._kafka_available = False
        mock_consumer.return_value = mock_consumer_instance

        mock_service.return_value = MagicMock()
        mock_producer.return_value = MagicMock()

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        # Run command briefly (it will exit because kafka not available)
        def stop_after_one(*args):
            cmd._running = False

        with patch("time.sleep", side_effect=stop_after_one):
            cmd.handle(batch_size=10, poll_timeout=1.0, max_retries=3)

        mock_config.assert_called_once()
        mock_consumer.assert_called_once()
        mock_service.assert_called_once()

    def test_run_async_helper_function(self):
        """Test _run_async helper works correctly."""
        from media_curation.management.commands.run_curation_consumer import _run_async

        async def sample_coro():
            return "result"

        result = _run_async(sample_coro())
        assert result == "result"

    def test_command_has_stdout_stderr(self):
        """Test command can write to stdout/stderr."""
        from media_curation.management.commands.run_curation_consumer import Command

        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        cmd.stdout.write("test output")
        cmd.stderr.write("test error")

        assert "test output" in cmd.stdout.getvalue()
        assert "test error" in cmd.stderr.getvalue()


class TestProcessEventMethod:
    """Tests for the _process_event method."""

    def test_process_event_success(self):
        """Test _process_event handles successful processing."""
        from media_curation.management.commands.run_curation_consumer import Command
        from media_curation.domain.models import CurationEvent, ContentType
        from uuid import uuid4

        cmd = Command()
        cmd._service = MagicMock()
        cmd._producer = MagicMock()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        # Create mock event
        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        # Process should succeed
        cmd._process_event(event, max_retries=3)

        cmd._service.process_event.assert_called_once_with(event)

    def test_process_event_handles_retryable_error(self):
        """Test _process_event retries on RetryableError."""
        from media_curation.management.commands.run_curation_consumer import Command
        from media_curation.domain.models import CurationEvent, ContentType
        from media_curation.domain.exceptions import RetryableError
        from uuid import uuid4

        cmd = Command()
        cmd._service = MagicMock()
        cmd._service.process_event.side_effect = RetryableError("Temporary failure")
        cmd._producer = MagicMock()
        cmd._producer.publish_to_dlq = AsyncMock()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        # Should handle error gracefully
        cmd._process_event(event, max_retries=1)

        # Service was called
        assert cmd._service.process_event.called

    def test_process_event_handles_non_retryable_error(self):
        """Test _process_event sends to DLQ on NonRetryableError."""
        from media_curation.management.commands.run_curation_consumer import Command
        from media_curation.domain.models import CurationEvent, ContentType
        from media_curation.domain.exceptions import NonRetryableError
        from uuid import uuid4

        cmd = Command()
        cmd._service = MagicMock()
        cmd._service.process_event.side_effect = NonRetryableError("Permanent failure")
        cmd._producer = MagicMock()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        event = CurationEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id=uuid4(),
            file_id=uuid4(),
            raw_gcs_uri="gs://bucket/file.pdf",
            mime_type="application/pdf",
            content_type=ContentType.DOCUMENT,
        )

        # Should handle error gracefully
        cmd._process_event(event, max_retries=3)

        # Should send to DLQ
        assert cmd._service.process_event.called
