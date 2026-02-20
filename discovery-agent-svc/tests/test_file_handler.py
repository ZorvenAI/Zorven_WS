"""Tests for FileHandler — GCS upload and ingestion event emission."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.services.file_handler import FileHandler


class TestGCSUpload:
    """GCS upload tests."""

    async def test_stub_mode_returns_original_url(self) -> None:
        handler = FileHandler(gcs_project_id="", gcs_bucket="")
        result = await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"%PDF-1.4 content",
            tenant_id="tenant-1",
            job_id="job-1",
        )
        assert result.type == "document"
        assert result.title == "report.pdf"
        assert result.url == "https://example.com/report.pdf"

    async def test_stub_mode_does_not_upload(self) -> None:
        handler = FileHandler(gcs_project_id="", gcs_bucket="")
        # Should not try to create GCS client
        assert handler._stub_mode is True
        result = await handler.handle_downloadable(
            url="https://example.com/data.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content_bytes=b"excel content",
            tenant_id="tenant-1",
        )
        assert result.type == "document"

    async def test_gcs_upload_on_success(self) -> None:
        handler = FileHandler(
            gcs_project_id="test-project",
            gcs_bucket="test-bucket",
        )
        handler._stub_mode = False

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        handler._gcs_client = mock_client

        result = await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"pdf content",
            tenant_id="tenant-1",
            job_id="job-1",
        )

        mock_blob.upload_from_string.assert_called_once()
        assert result.url.startswith("gs://test-bucket/_landing/")
        assert result.type == "document"

    async def test_gcs_upload_error_falls_back_to_url(self) -> None:
        handler = FileHandler(
            gcs_project_id="test-project",
            gcs_bucket="test-bucket",
        )
        handler._stub_mode = False

        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_blob = MagicMock()
        mock_blob.upload_from_string.side_effect = Exception("GCS error")
        mock_client.bucket.return_value = mock_bucket
        mock_bucket.blob.return_value = mock_blob
        handler._gcs_client = mock_client

        result = await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"pdf content",
            tenant_id="tenant-1",
        )
        assert result.url == "https://example.com/report.pdf"


class TestIngestionEvent:
    """Kafka ingestion event emission tests."""

    async def test_emits_ingestion_event(self) -> None:
        mock_producer = MagicMock()
        mock_kafka = AsyncMock()
        mock_producer._producer = mock_kafka

        handler = FileHandler(kafka_producer=mock_producer)
        await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"pdf content",
            tenant_id="tenant-1",
            job_id="job-1",
        )
        mock_kafka.send_and_wait.assert_called_once()
        topic = mock_kafka.send_and_wait.call_args.args[0]
        assert topic == "raw-ingestion-topic"

    async def test_ingestion_event_has_correct_fields(self) -> None:
        import json

        mock_producer = MagicMock()
        mock_kafka = AsyncMock()
        mock_producer._producer = mock_kafka

        handler = FileHandler(kafka_producer=mock_producer)
        await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"pdf content",
            tenant_id="tenant-1",
            job_id="job-1",
        )

        raw_event = mock_kafka.send_and_wait.call_args.args[1]
        event = json.loads(raw_event)
        assert event["source"] == "api-integration"
        assert event["tenant_id"] == "tenant-1"
        assert event["file_type"] == "application/pdf"
        assert event["metadata"]["source_url"] == "https://example.com/report.pdf"
        assert event["metadata"]["job_id"] == "job-1"
        assert "event_id" in event
        assert "trace_id" in event

    async def test_no_kafka_producer_skips_event(self) -> None:
        handler = FileHandler(kafka_producer=None)
        # Should not raise
        result = await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"pdf",
            tenant_id="tenant-1",
        )
        assert result.type == "document"

    async def test_kafka_error_does_not_crash(self) -> None:
        mock_producer = MagicMock()
        mock_kafka = AsyncMock()
        mock_kafka.send_and_wait = AsyncMock(side_effect=Exception("Kafka down"))
        mock_producer._producer = mock_kafka

        handler = FileHandler(kafka_producer=mock_producer)
        result = await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"pdf",
            tenant_id="tenant-1",
        )
        assert result.type == "document"
