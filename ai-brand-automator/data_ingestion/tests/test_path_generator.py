"""
Unit tests for path generator.

Tests GCS path generation and parsing logic.
"""

import pytest
from datetime import datetime

from data_ingestion.domain.path_generator import (
    generate_raw_path,
    parse_gcs_uri,
    sanitize_tenant_id,
    extract_filename,
    extract_object_path,
)
from data_ingestion.domain.exceptions import PathGenerationError


class TestExtractObjectPath:
    """Tests for extract_object_path shared utility."""

    def test_gs_uri_full(self):
        assert extract_object_path("gs://bucket/1/raw/2026/02/06/file.png") == "1/raw/2026/02/06/file.png"

    def test_gs_uri_bucket_only(self):
        assert extract_object_path("gs://bucket-only") == "bucket-only"

    def test_plain_path_returned_as_is(self):
        assert extract_object_path("1/raw/2026/02/06/file.png") == "1/raw/2026/02/06/file.png"

    def test_plain_path_with_leading_slash(self):
        assert extract_object_path("/1/raw/file.png") == "1/raw/file.png"

    def test_empty_string(self):
        assert extract_object_path("") == ""

    def test_non_gs_scheme(self):
        """Non-gs:// schemes are treated as plain paths."""
        assert extract_object_path("s3://bucket/key") == "s3://bucket/key"


class TestParseGcsUri:
    """Tests for parse_gcs_uri function."""

    def test_valid_gcs_uri(self):
        """Test parsing a valid GCS URI."""
        bucket, blob = parse_gcs_uri("gs://my-bucket/path/to/file.mp4")
        assert bucket == "my-bucket"
        assert blob == "path/to/file.mp4"

    def test_valid_gcs_uri_landing_zone(self):
        """Test parsing a landing zone URI."""
        bucket, blob = parse_gcs_uri("gs://onboarding-bucket1/_landing/video.mp4")
        assert bucket == "onboarding-bucket1"
        assert blob == "_landing/video.mp4"

    def test_nested_path(self):
        """Test parsing a deeply nested path."""
        bucket, blob = parse_gcs_uri("gs://bucket/a/b/c/d/e/file.mp4")
        assert bucket == "bucket"
        assert blob == "a/b/c/d/e/file.mp4"

    def test_file_at_root(self):
        """Test parsing a file at bucket root."""
        bucket, blob = parse_gcs_uri("gs://bucket/file.mp4")
        assert bucket == "bucket"
        assert blob == "file.mp4"

    def test_invalid_uri_not_gcs(self):
        """Test that non-GCS URIs raise error."""
        with pytest.raises(PathGenerationError, match="Invalid GCS URI"):
            parse_gcs_uri("s3://bucket/file.mp4")

    def test_invalid_uri_local_path(self):
        """Test that local paths raise error."""
        with pytest.raises(PathGenerationError, match="Invalid GCS URI"):
            parse_gcs_uri("/local/path/file.mp4")

    def test_invalid_uri_no_path(self):
        """Test that bucket-only URI raises error."""
        with pytest.raises(PathGenerationError, match="Invalid GCS URI"):
            parse_gcs_uri("gs://bucket")

    def test_empty_uri(self):
        """Test that empty URI raises error."""
        with pytest.raises(PathGenerationError, match="Invalid GCS URI"):
            parse_gcs_uri("")


class TestExtractFilename:
    """Tests for extract_filename function."""

    def test_simple_filename(self):
        """Test extracting a simple filename."""
        assert extract_filename("_landing/file.mp4") == "file.mp4"

    def test_nested_path(self):
        """Test extracting filename from nested path."""
        assert extract_filename("a/b/c/file.mp4") == "file.mp4"

    def test_filename_only(self):
        """Test extracting when only filename is present."""
        assert extract_filename("file.mp4") == "file.mp4"


class TestSanitizeTenantId:
    """Tests for sanitize_tenant_id function."""

    def test_valid_tenant_id(self):
        """Test that valid tenant IDs pass through (normalized to lowercase)."""
        assert sanitize_tenant_id("tenant-123") == "tenant-123"
        assert sanitize_tenant_id("TENANT_456") == "tenant_456"

    def test_special_characters_removed(self):
        """Test that special characters are removed."""
        assert sanitize_tenant_id("tenant/123") == "tenant123"
        assert sanitize_tenant_id("tenant\\123") == "tenant123"
        assert sanitize_tenant_id("tenant:123") == "tenant123"

    def test_spaces_replaced(self):
        """Test that spaces are replaced with hyphens."""
        assert sanitize_tenant_id("tenant 123") == "tenant-123"

    def test_empty_tenant_id(self):
        """Test that empty tenant ID raises error."""
        with pytest.raises(PathGenerationError, match="tenant_id cannot be empty"):
            sanitize_tenant_id("")

    def test_whitespace_only(self):
        """Test that whitespace-only tenant ID raises error."""
        with pytest.raises(PathGenerationError, match="no valid characters"):
            sanitize_tenant_id("   ")


class TestGenerateRawPath:
    """Tests for generate_raw_path function."""

    def test_basic_path_generation(self):
        """Test basic path generation."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://onboarding-bucket1/_landing/video.mp4",
            timestamp=datetime(2026, 1, 29, 14, 30, 0),
        )

        assert result == "gs://onboarding-bucket1/tenant-123/raw/2026/01/29/video.mp4"

    def test_preserves_filename(self):
        """Test that original filename is preserved."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/my-special-file.mp4",
            timestamp=datetime(2026, 1, 29),
        )

        assert result.endswith("my-special-file.mp4")

    def test_date_partitioning(self):
        """Test date-based directory partitioning."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/file.mp4",
            timestamp=datetime(2026, 12, 31),
        )

        assert "/2026/12/31/" in result

    def test_different_bucket(self):
        """Test path generation preserves source bucket."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://other-bucket/_landing/file.mp4",
            timestamp=datetime(2026, 1, 29),
        )

        assert result.startswith("gs://other-bucket/")

    def test_nested_source_path(self):
        """Test with nested source path."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/subfolder/deep/file.mp4",
            timestamp=datetime(2026, 1, 29),
        )

        # Should extract just the filename
        assert result.endswith("file.mp4")

    def test_tenant_id_sanitization(self):
        """Test that tenant ID is sanitized (special chars removed)."""
        result = generate_raw_path(
            tenant_id="tenant/with/slashes",
            source_path="gs://bucket/_landing/file.mp4",
            timestamp=datetime(2026, 1, 29),
        )

        # Slashes should be removed
        assert "/tenant/with/slashes/" not in result
        assert "tenantwithslashes" in result

    def test_invalid_source_path(self):
        """Test that invalid source path raises error."""
        with pytest.raises(PathGenerationError):
            generate_raw_path(
                tenant_id="tenant-123",
                source_path="/local/path/file.mp4",
                timestamp=datetime(2026, 1, 29),
            )

    def test_empty_tenant_id(self):
        """Test that empty tenant ID raises error."""
        with pytest.raises(PathGenerationError):
            generate_raw_path(
                tenant_id="",
                source_path="gs://bucket/_landing/file.mp4",
                timestamp=datetime(2026, 1, 29),
            )


class TestPathGenerationEdgeCases:
    """Edge case tests for path generation."""

    def test_file_with_spaces(self):
        """Test filename with spaces."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/my file with spaces.mp4",
            timestamp=datetime(2026, 1, 29),
        )

        assert "my file with spaces.mp4" in result or "my%20file" in result

    def test_file_with_unicode(self):
        """Test filename with unicode characters."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/vidéo_français.mp4",
            timestamp=datetime(2026, 1, 29),
        )

        assert result.endswith(".mp4")

    def test_various_extensions(self):
        """Test various file extensions."""
        for ext in [".mp4", ".mov", ".avi", ".pdf", ".jpg", ".png"]:
            result = generate_raw_path(
                tenant_id="tenant-123",
                source_path=f"gs://bucket/_landing/file{ext}",
                timestamp=datetime(2026, 1, 29),
            )
            assert result.endswith(ext)

    def test_no_extension(self):
        """Test file without extension."""
        result = generate_raw_path(
            tenant_id="tenant-123",
            source_path="gs://bucket/_landing/README",
            timestamp=datetime(2026, 1, 29),
        )

        assert result.endswith("README")
