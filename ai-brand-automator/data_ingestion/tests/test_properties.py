"""
Property-based tests using Hypothesis.

Tests the data ingestion pipeline with randomly generated inputs
to discover edge cases and ensure robustness.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from hypothesis import given, strategies as st, assume, settings

from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessedEvent,
    ProcessingStatus,
    EventSource,
)
from data_ingestion.domain.path_generator import (
    generate_raw_path,
    parse_gcs_uri,
    sanitize_tenant_id,
)


# =============================================================================
# Custom Strategies
# =============================================================================


@st.composite
def valid_tenant_ids(draw):
    """Generate valid tenant IDs (alphanumeric, hyphens, underscores only)."""
    # Start with a letter
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
    rest = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
            min_size=0,
            max_size=50,
        )
    )
    return first_char + rest


@st.composite
def valid_gcs_paths(draw):
    """Generate valid GCS paths."""
    bucket = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=3,
            max_size=30,
        )
    )
    # Ensure bucket starts with letter
    bucket = "a" + bucket[1:] if bucket else "abucket"

    filename = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
            min_size=1,
            max_size=50,
        )
    )
    extension = draw(st.sampled_from([".mp4", ".mov", ".avi", ".pdf", ".jpg", ".png"]))

    return f"gs://{bucket}/_landing/{filename}{extension}"


@st.composite
def valid_ingestion_events(draw):
    """Generate valid IngestionEvent instances."""
    event_id = uuid4()
    trace_id = uuid4()
    tenant_id = draw(valid_tenant_ids())
    file_path = draw(valid_gcs_paths())
    timestamp = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
        )
    )
    source = draw(st.sampled_from(list(EventSource)))

    return IngestionEvent(
        event_id=event_id,
        trace_id=trace_id,
        tenant_id=tenant_id,
        file_path=file_path,
        file_type="video/mp4",
        timestamp=timestamp,
        source=source,
    )


# =============================================================================
# Property Tests: Tenant ID Sanitization
# =============================================================================


@pytest.mark.property
class TestTenantIdProperties:
    """Property tests for tenant ID handling."""

    @given(tenant_id=valid_tenant_ids())
    def test_sanitized_tenant_id_is_valid_path_component(self, tenant_id):
        """Sanitized tenant IDs should be valid path components."""
        assume(len(tenant_id.strip()) > 0)

        sanitized = sanitize_tenant_id(tenant_id)

        # Should not contain path separators
        assert "/" not in sanitized
        assert "\\" not in sanitized
        assert ":" not in sanitized

        # Should not be empty
        assert len(sanitized) > 0

    @given(tenant_id=valid_tenant_ids())
    def test_sanitization_is_idempotent(self, tenant_id):
        """Sanitizing twice should give the same result."""
        assume(len(tenant_id.strip()) > 0)

        first = sanitize_tenant_id(tenant_id)
        second = sanitize_tenant_id(first)
        assert first == second


# =============================================================================
# Property Tests: GCS URI Parsing
# =============================================================================


@pytest.mark.property
class TestGcsUriProperties:
    """Property tests for GCS URI parsing."""

    @given(gcs_path=valid_gcs_paths())
    def test_parse_gcs_uri_extracts_bucket_and_blob(self, gcs_path):
        """parse_gcs_uri should extract bucket and blob correctly."""
        bucket, blob = parse_gcs_uri(gcs_path)

        # Bucket should be non-empty
        assert len(bucket) > 0

        # Blob should be non-empty
        assert len(blob) > 0

        # Reconstructed path should match original
        assert f"gs://{bucket}/{blob}" == gcs_path

    @given(
        bucket=st.text(
            min_size=3, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789-"
        ),
        blob=st.text(
            min_size=1,
            max_size=100,
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_./",
        ),
    )
    def test_parse_roundtrip(self, bucket, blob):
        """Parsing a constructed URI should give back the components."""
        assume(len(bucket) >= 3)
        assume(len(blob) >= 1)
        assume(not blob.startswith("/"))

        uri = f"gs://{bucket}/{blob}"
        parsed_bucket, parsed_blob = parse_gcs_uri(uri)

        assert parsed_bucket == bucket
        assert parsed_blob == blob


# =============================================================================
# Property Tests: Path Generation
# =============================================================================


@pytest.mark.property
class TestPathGenerationProperties:
    """Property tests for path generation."""

    @given(event=valid_ingestion_events())
    @settings(max_examples=50)
    def test_generated_path_preserves_bucket(self, event):
        """Generated path should use the same bucket as source."""
        result = generate_raw_path(
            tenant_id=event.tenant_id,
            source_path=event.file_path,
            timestamp=event.timestamp,
        )

        source_bucket, _ = parse_gcs_uri(event.file_path)
        dest_bucket, _ = parse_gcs_uri(result)

        assert source_bucket == dest_bucket

    @given(event=valid_ingestion_events())
    @settings(max_examples=50)
    def test_generated_path_includes_raw_directory(self, event):
        """Generated path should include 'raw' directory."""
        result = generate_raw_path(
            tenant_id=event.tenant_id,
            source_path=event.file_path,
            timestamp=event.timestamp,
        )

        assert "/raw/" in result

    @given(event=valid_ingestion_events())
    @settings(max_examples=50)
    def test_generated_path_includes_date_partitioning(self, event):
        """Generated path should include date-based partitioning."""
        result = generate_raw_path(
            tenant_id=event.tenant_id,
            source_path=event.file_path,
            timestamp=event.timestamp,
        )

        year = str(event.timestamp.year)
        month = f"{event.timestamp.month:02d}"
        day = f"{event.timestamp.day:02d}"

        assert f"/{year}/{month}/{day}/" in result

    @given(event=valid_ingestion_events())
    @settings(max_examples=50)
    def test_generated_path_preserves_extension(self, event):
        """Generated path should preserve file extension."""
        result = generate_raw_path(
            tenant_id=event.tenant_id,
            source_path=event.file_path,
            timestamp=event.timestamp,
        )

        # Extract extension from source
        source_ext = event.file_path.rsplit(".", 1)[-1]
        assert result.endswith(f".{source_ext}")


# =============================================================================
# Property Tests: ProcessedEvent Model
# =============================================================================


@pytest.mark.property
class TestProcessedEventProperties:
    """Property tests for ProcessedEvent model."""

    @given(
        duration=st.integers(min_value=0, max_value=1000000),
        status=st.sampled_from(list(ProcessingStatus)),
    )
    def test_processed_event_creation(self, duration, status):
        """ProcessedEvent should accept valid inputs."""
        event = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            timestamp=datetime.utcnow(),
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="gs://bucket/tenant-123/raw/2026/01/29/file.mp4",
            status=status,
            processing_duration_ms=duration,
        )

        assert event.processing_duration_ms == duration
        assert event.status == status
