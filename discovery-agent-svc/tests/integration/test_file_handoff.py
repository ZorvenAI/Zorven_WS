"""Integration test: GCS + ingestion handoff for downloadable files.

Verifies that downloadable files (PDF, Excel) are detected correctly
and routed through FileHandler instead of the HTML cleaning pipeline.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.scrapers.browser_engine import ScrapeResult
from app.scrapers.data_cleaner import DataCleaner
from app.services.file_handler import FileHandler

pytestmark = pytest.mark.integration


class TestFileDetection:
    """Verify downloadable file detection in the execute flow."""

    async def test_pdf_detected_as_downloadable(self) -> None:
        cleaner = DataCleaner()
        assert cleaner.is_downloadable("report.pdf", "application/pdf") is True

    async def test_excel_detected_as_downloadable(self) -> None:
        cleaner = DataCleaner()
        assert cleaner.is_downloadable(
            "data.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ) is True

    async def test_html_not_downloadable(self) -> None:
        cleaner = DataCleaner()
        assert cleaner.is_downloadable("page.html", "text/html") is False


class TestFileHandlerStubMode:
    """FileHandler in stub mode (no GCS credentials)."""

    async def test_stub_mode_returns_source_with_original_url(self) -> None:
        handler = FileHandler(gcs_project_id="", gcs_bucket="")
        result = await handler.handle_downloadable(
            url="https://example.com/report.pdf",
            content_type="application/pdf",
            content_bytes=b"%PDF-1.4 content",
            tenant_id="tenant-1",
            job_id="job-1",
        )
        assert result.type == "document"
        assert result.url == "https://example.com/report.pdf"
        assert result.title == "report.pdf"

    async def test_stub_mode_no_gcs_upload(self) -> None:
        handler = FileHandler(gcs_project_id="", gcs_bucket="")
        assert handler._stub_mode is True


class TestFileHandlerGCSUpload:
    """FileHandler with mocked GCS."""

    async def test_gcs_upload_success(self) -> None:
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

    async def test_gcs_error_returns_original_url(self) -> None:
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


class TestIngestionEventEmission:
    """Verify IngestionEvent is emitted to raw-ingestion-topic."""

    async def test_ingestion_event_matches_schema(self) -> None:
        mock_producer = MagicMock()
        mock_kafka = AsyncMock()
        mock_producer._producer = mock_kafka

        handler = FileHandler(kafka_producer=mock_producer)
        await handler.handle_downloadable(
            url="https://example.com/data.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content_bytes=b"excel content",
            tenant_id="tenant-1",
            job_id="job-42",
        )

        mock_kafka.send_and_wait.assert_called_once()
        topic, raw_event = mock_kafka.send_and_wait.call_args.args
        assert topic == "raw-ingestion-topic"

        event = json.loads(raw_event)
        assert event["source"] == "api-integration"
        assert event["tenant_id"] == "tenant-1"
        assert event["file_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert event["metadata"]["source_url"] == "https://example.com/data.xlsx"
        assert event["metadata"]["job_id"] == "job-42"
        assert "event_id" in event
        assert "trace_id" in event
        assert "timestamp" in event

    async def test_kafka_unavailable_does_not_crash(self) -> None:
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
