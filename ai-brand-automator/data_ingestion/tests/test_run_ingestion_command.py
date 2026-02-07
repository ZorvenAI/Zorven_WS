"""
Tests for run_ingestion management command helpers.

Tests _extract_gcs_path, _update_asset_status, and _process_event
to ensure BrandAsset status and gcs_path are updated correctly.
"""

import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from data_ingestion.management.commands.run_ingestion import (
    _extract_gcs_path,
    _update_asset_status,
)


# =============================================================================
# _extract_gcs_path tests
# =============================================================================


class TestExtractGcsPath:
    """Tests for extracting object path from gs:// URIs."""

    def test_full_uri(self):
        uri = "gs://my-bucket/1/raw/2026/02/06/file.png"
        assert _extract_gcs_path(uri) == "1/raw/2026/02/06/file.png"

    def test_nested_path(self):
        uri = "gs://bucket/tenant/raw/subdir/image.jpg"
        assert _extract_gcs_path(uri) == "tenant/raw/subdir/image.jpg"

    def test_no_gs_prefix(self):
        """If no gs:// prefix, returns the path unchanged."""
        path = "bucket/some/path.txt"
        assert _extract_gcs_path(path) == "bucket/some/path.txt"

    def test_bucket_only(self):
        """Edge case: URI with bucket but no path returns bucket name."""
        uri = "gs://bucket-only"
        assert _extract_gcs_path(uri) == "bucket-only"

    def test_empty_string(self):
        assert _extract_gcs_path("") == ""


# =============================================================================
# _update_asset_status tests
# =============================================================================


@pytest.mark.django_db
class TestUpdateAssetStatus:
    """Tests for updating BrandAsset pipeline status from ingestion."""

    @pytest.fixture
    def brand_asset(self):
        """Create a BrandAsset for testing."""
        from onboarding.models import BrandAsset, Company
        from tenants.models import Tenant, Domain

        tenant, _ = Tenant.objects.get_or_create(
            schema_name="public",
            defaults={"name": "public"},
        )
        Domain.objects.get_or_create(
            domain="localhost",
            defaults={"tenant": tenant, "is_primary": True},
        )

        company = Company.objects.create(
            tenant=tenant,
            name="Test Company",
            industry="Technology",
        )
        asset = BrandAsset.objects.create(
            tenant=tenant,
            company=company,
            file_name="test.png",
            file_type="image",
            file_size=1024,
            gcs_path="1/_landing/test.png",
            pipeline_status="pending",
        )
        return asset

    def test_update_status_to_ingested(self, brand_asset):
        """Successful ingestion sets status to 'ingested'."""
        result = _update_asset_status(str(brand_asset.id), "ingested")
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.pipeline_status == "ingested"

    def test_update_status_to_failed(self, brand_asset):
        """Failed ingestion sets status and error message."""
        result = _update_asset_status(
            str(brand_asset.id), "failed", error_msg="File corrupt"
        )
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.pipeline_status == "failed"
        assert brand_asset.pipeline_error == "File corrupt"

    def test_clears_error_on_success(self, brand_asset):
        """Re-ingestion clears previous pipeline_error."""
        # Simulate a previous failure
        brand_asset.pipeline_status = "failed"
        brand_asset.pipeline_error = "Old error"
        brand_asset.save()

        result = _update_asset_status(str(brand_asset.id), "ingested")
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.pipeline_status == "ingested"
        assert brand_asset.pipeline_error == ""

    def test_updates_gcs_path(self, brand_asset):
        """Successful ingestion updates gcs_path to new location."""
        new_uri = "gs://my-bucket/1/raw/2026/02/06/test.png"
        result = _update_asset_status(
            str(brand_asset.id), "ingested", new_gcs_path=new_uri
        )
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.gcs_path == "1/raw/2026/02/06/test.png"

    def test_lookup_by_uuid(self, brand_asset):
        """Can look up asset by pipeline_trace_id UUID."""
        trace_id = uuid.uuid4()
        brand_asset.pipeline_trace_id = trace_id
        brand_asset.save()

        result = _update_asset_status(str(trace_id), "ingested")
        assert result is True

        brand_asset.refresh_from_db()
        assert brand_asset.pipeline_status == "ingested"

    def test_asset_not_found(self):
        """Returns False when asset ID doesn't exist."""
        result = _update_asset_status("999999", "ingested")
        assert result is False

    def test_invalid_id_returns_false(self):
        """Returns False for non-existent UUID."""
        result = _update_asset_status(str(uuid.uuid4()), "ingested")
        assert result is False


# =============================================================================
# _process_event integration tests
# =============================================================================


class TestProcessEvent:
    """Tests for _process_event updating BrandAsset on success/failure."""

    @pytest.fixture
    def command(self):
        """Create a Command instance with mocked service."""
        from data_ingestion.management.commands.run_ingestion import Command

        cmd = Command()
        cmd._service = MagicMock()
        return cmd

    @pytest.fixture
    def ingestion_event(self):
        """Create a test IngestionEvent with all required fields."""
        from data_ingestion.domain.models import IngestionEvent, EventSource

        return IngestionEvent(
            event_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
            tenant_id="tenant-1",
            file_path="gs://bucket/1/_landing/test.png",
            file_type="image/png",
            metadata={"asset_id": "42"},
        )

    def test_successful_processing_calls_update(self, command, ingestion_event):
        """On success, _update_asset_status is called with 'ingested'."""
        mock_result = MagicMock()
        mock_result.destination_path = "gs://bucket/1/raw/2026/02/06/test.png"
        command._service.process_event_with_retry.return_value = mock_result

        with patch(
            "data_ingestion.management.commands.run_ingestion._update_asset_status"
        ) as mock_update:
            command._process_event(ingestion_event)
            mock_update.assert_called_once_with(
                "42",
                "ingested",
                new_gcs_path="gs://bucket/1/raw/2026/02/06/test.png",
            )

    def test_non_retryable_failure_calls_update(self, command, ingestion_event):
        """On NonRetryableError, status set to 'failed' with error."""
        from data_ingestion.domain.exceptions import NonRetryableError

        command._service.process_event_with_retry.side_effect = NonRetryableError(
            "Bad file format"
        )
        command._service.send_to_dlq = MagicMock()

        with patch(
            "data_ingestion.management.commands.run_ingestion._update_asset_status"
        ) as mock_update:
            command._process_event(ingestion_event)
            mock_update.assert_called_once()
            args = mock_update.call_args[0]
            assert args[0] == "42"
            assert args[1] == "failed"
            assert "Bad file format" in args[2]

    def test_retryable_failure_calls_update(self, command, ingestion_event):
        """On RetryableError (exhausted), status set to 'failed'."""
        from data_ingestion.domain.exceptions import RetryableError

        command._service.process_event_with_retry.side_effect = RetryableError(
            "Timeout"
        )
        command._service.send_to_dlq = MagicMock()

        with patch(
            "data_ingestion.management.commands.run_ingestion._update_asset_status"
        ) as mock_update:
            command._process_event(ingestion_event)
            mock_update.assert_called_once()
            args = mock_update.call_args[0]
            assert args[0] == "42"
            assert args[1] == "failed"
            assert "Timeout" in args[2]

    def test_duplicate_event_skips_update(self, command, ingestion_event):
        """Duplicate (None result) does not call _update_asset_status."""
        command._service.process_event_with_retry.return_value = None

        with patch(
            "data_ingestion.management.commands.run_ingestion._update_asset_status"
        ) as mock_update:
            command._process_event(ingestion_event)
            mock_update.assert_not_called()

    def test_no_asset_id_skips_update(self, command):
        """Events without asset_id in metadata skip the update."""
        from data_ingestion.domain.models import IngestionEvent, EventSource

        event = IngestionEvent(
            event_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            timestamp=datetime.utcnow(),
            source=EventSource.FRONTEND_UPLOAD,
            tenant_id="tenant-1",
            file_path="gs://bucket/1/_landing/noasset.png",
            file_type="image/png",
            metadata={},
        )
        mock_result = MagicMock()
        mock_result.destination_path = "gs://bucket/1/raw/file.png"
        command._service.process_event_with_retry.return_value = mock_result

        with patch(
            "data_ingestion.management.commands.run_ingestion._update_asset_status"
        ) as mock_update:
            command._process_event(event)
            mock_update.assert_not_called()
