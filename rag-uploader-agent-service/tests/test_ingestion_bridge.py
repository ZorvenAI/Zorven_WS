"""Tests for IngestionBridge."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.logic.ingestion_bridge import IngestionBridge


class TestIngestionBridge:
    """Tests for ingestion event emission."""

    async def test_emit_success(self):
        mock_producer = AsyncMock()
        mock_producer.send_ingestion_event.return_value = True

        bridge = IngestionBridge(ingestion_producer=mock_producer)
        result = await bridge.emit(
            file_path="gs://bucket/path/file.pdf",
            file_type="application/pdf",
            file_size_bytes=1024,
            tenant_id="test-tenant",
            metadata={"custom_title": "My Report"},
        )

        assert result is True
        mock_producer.send_ingestion_event.assert_called_once()
        event = mock_producer.send_ingestion_event.call_args[0][0]
        assert event["file_path"] == "gs://bucket/path/file.pdf"
        assert event["source"] == "api-integration"
        assert event["tenant_id"] == "test-tenant"

    async def test_emit_kafka_failure_returns_false(self):
        mock_producer = AsyncMock()
        mock_producer.send_ingestion_event.return_value = False

        bridge = IngestionBridge(ingestion_producer=mock_producer)
        result = await bridge.emit(
            file_path="gs://bucket/file.pdf",
            file_type="application/pdf",
            file_size_bytes=0,
            tenant_id="t",
            metadata={},
        )

        assert result is False

    async def test_event_format_matches_ingestion_schema(self):
        mock_producer = AsyncMock()
        mock_producer.send_ingestion_event.return_value = True

        bridge = IngestionBridge(ingestion_producer=mock_producer)
        await bridge.emit(
            file_path="gs://bucket/file.pdf",
            file_type="application/pdf",
            file_size_bytes=2048,
            tenant_id="tenant-1",
            metadata={"original_name": "report.pdf"},
            trace_id="trace-abc",
        )

        event = mock_producer.send_ingestion_event.call_args[0][0]
        # Verify all required IngestionEvent fields
        assert "event_id" in event
        assert event["trace_id"] == "trace-abc"
        assert "timestamp" in event
        assert event["source"] == "api-integration"
        assert event["tenant_id"] == "tenant-1"
        assert event["file_path"] == "gs://bucket/file.pdf"
        assert event["file_type"] == "application/pdf"
        assert event["file_size_bytes"] == 2048
        assert event["metadata"]["original_name"] == "report.pdf"

    async def test_zero_file_size_sent_as_none(self):
        mock_producer = AsyncMock()
        mock_producer.send_ingestion_event.return_value = True

        bridge = IngestionBridge(ingestion_producer=mock_producer)
        await bridge.emit(
            file_path="gs://bucket/file.pdf",
            file_type="application/pdf",
            file_size_bytes=0,
            tenant_id="t",
            metadata={},
        )

        event = mock_producer.send_ingestion_event.call_args[0][0]
        assert event["file_size_bytes"] is None
