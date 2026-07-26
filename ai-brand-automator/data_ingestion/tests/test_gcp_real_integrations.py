"""
Real Google Cloud Storage Integration Tests for Data Ingestion Service.

These tests connect to actual Google Cloud Storage to verify the
GCSAdapter works correctly with real file operations.

Prerequisites:
- Valid GCP service account credentials in credentials/gcs-credentials.json
- Test bucket: zorven-raw-assets

Run with:
    GOOGLE_APPLICATION_CREDENTIALS=credentials/gcs-credentials.json \
    pytest data_ingestion/tests/test_gcp_real_integrations.py -v

Note: These tests create and delete files in GCS for testing purposes.
"""

import os
import pytest
from pathlib import Path
from uuid import uuid4

# Mark all tests as requiring real GCP credentials
pytestmark = [pytest.mark.integration, pytest.mark.gcp]

# Test configuration - HARDCODED for real GCP tests
# These override the .env.test values which use mock buckets
GCP_PROJECT_ID = "zorven-503517"
TEST_BUCKET = "zorven-raw-assets"
TEST_PREFIX = "test-ingestion"


def get_credentials_path():
    """Get absolute path to GCP credentials file."""
    base_dir = Path(__file__).parent.parent.parent
    creds_path = base_dir / "credentials" / "gcs-credentials.json"
    return str(creds_path)


def setup_gcp_credentials():
    """Set up GCP credentials for testing."""
    creds_path = get_credentials_path()
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        return True
    return False


# =============================================================================
# GCS Adapter Real Connection Tests
# =============================================================================


class TestGCSAdapterRealConnection:
    """
    Tests for GCSAdapter with real GCS connection.

    These tests verify that the adapter can:
    - Initialize with real GCP credentials
    - Check if files exist
    - Get file metadata
    - Move, copy, and delete files
    - List files with prefix
    """

    @pytest.fixture(autouse=True)
    def setup_credentials(self):
        """Ensure GCP credentials are set."""
        if not setup_gcp_credentials():
            pytest.skip("GCP credentials not found")

    @pytest.fixture
    def gcs_adapter(self):
        """Create a real GCSAdapter instance."""
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        return GCSAdapter(
            project_id=GCP_PROJECT_ID,
            default_bucket=TEST_BUCKET,
        )

    def test_gcs_adapter_initialization(self):
        """Test GCSAdapter initializes with real project credentials."""
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        adapter = GCSAdapter(
            project_id=GCP_PROJECT_ID,
            default_bucket=TEST_BUCKET,
        )

        assert adapter.project_id == GCP_PROJECT_ID
        assert adapter.default_bucket == TEST_BUCKET
        assert adapter.client is not None
        print(f"✅ GCS adapter initialized for project: {adapter.project_id}")

    def test_gcs_adapter_with_explicit_credentials(self):
        """Test GCSAdapter with explicit credentials path."""
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        creds_path = get_credentials_path()
        adapter = GCSAdapter(
            project_id=GCP_PROJECT_ID,
            credentials_path=creds_path,
            default_bucket=TEST_BUCKET,
        )

        assert adapter.project_id == GCP_PROJECT_ID
        assert adapter.client is not None
        print("✅ GCS adapter initialized with explicit credentials")

    def test_check_exists_returns_true(self, gcs_adapter):
        """Test check_exists returns True for existing file."""
        # Use a known test file
        test_uri = (
            f"gs://{TEST_BUCKET}/customer-1/customer-1-onboarding-file-example-1.txt"
        )

        result = gcs_adapter.check_exists(test_uri)

        assert result is True
        print(f"✅ File exists: {test_uri}")

    def test_check_exists_returns_false(self, gcs_adapter):
        """Test check_exists returns False for non-existing file."""
        test_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/non-existent-file-{uuid4()}.txt"

        result = gcs_adapter.check_exists(test_uri)

        assert result is False
        print("✅ File correctly reported as not existing")

    def test_get_metadata_for_existing_file(self, gcs_adapter):
        """Test get_metadata returns correct metadata for existing file."""
        test_uri = (
            f"gs://{TEST_BUCKET}/customer-1/customer-1-onboarding-file-example-1.txt"
        )

        metadata = gcs_adapter.get_metadata(test_uri)

        assert metadata is not None
        assert metadata.bucket == TEST_BUCKET
        assert metadata.full_uri == test_uri
        assert metadata.size_bytes > 0
        assert metadata.content_type is not None
        print(
            f"✅ Got metadata: size={metadata.size_bytes}, type={metadata.content_type}"
        )

    def test_get_metadata_for_non_existing_file(self, gcs_adapter):
        """Test get_metadata raises error for non-existing file."""
        from data_ingestion.domain.exceptions import FileNotFoundInLandingError

        test_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/non-existent-{uuid4()}.txt"

        with pytest.raises(FileNotFoundInLandingError):
            gcs_adapter.get_metadata(test_uri)
        print("✅ Correctly raised FileNotFoundInLandingError")

    def test_list_files_with_prefix(self, gcs_adapter):
        """Test list_files returns files matching prefix."""
        # List files in customer-1 folder
        files = gcs_adapter.list_files("customer-1/", bucket_name=TEST_BUCKET)

        assert len(files) > 0
        assert all(f.startswith(f"gs://{TEST_BUCKET}/customer-1/") for f in files)
        print(f"✅ Listed {len(files)} files with prefix 'customer-1/'")

    def test_list_files_empty_result(self, gcs_adapter):
        """Test list_files returns empty list for non-matching prefix."""
        unique_prefix = f"non-existent-prefix-{uuid4()}/"
        files = gcs_adapter.list_files(unique_prefix, bucket_name=TEST_BUCKET)

        assert files == []
        print("✅ Correctly returned empty list for non-existent prefix")


class TestGCSAdapterFileOperations:
    """
    Tests for GCSAdapter file operations (upload, copy, move, delete).

    These tests create temporary files and clean them up after testing.
    """

    @pytest.fixture(autouse=True)
    def setup_credentials(self):
        """Ensure GCP credentials are set."""
        if not setup_gcp_credentials():
            pytest.skip("GCP credentials not found")

    @pytest.fixture
    def gcs_adapter(self):
        """Create a real GCSAdapter instance."""
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        return GCSAdapter(
            project_id=GCP_PROJECT_ID,
            default_bucket=TEST_BUCKET,
        )

    def test_upload_and_delete_file(self, gcs_adapter, tmp_path):
        """Test uploading a local file to GCS and then deleting it."""
        # Create a local test file
        test_id = str(uuid4())[:8]
        local_file = tmp_path / f"test-upload-{test_id}.txt"
        local_file.write_text("Test content for upload")

        dest_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/uploaded-{test_id}.txt"

        try:
            # Upload
            result = gcs_adapter.upload_file(str(local_file), dest_uri)
            assert result == dest_uri

            # Verify it exists
            assert gcs_adapter.check_exists(dest_uri) is True
            print(f"✅ Uploaded file: {dest_uri}")

        finally:
            # Cleanup
            gcs_adapter.delete_file(dest_uri)
            print(f"✅ Cleaned up: {dest_uri}")

    def test_copy_file(self, gcs_adapter, tmp_path):
        """Test copying a file within GCS."""
        test_id = str(uuid4())[:8]

        # Create source file
        local_file = tmp_path / f"test-copy-source-{test_id}.txt"
        local_file.write_text("Source content for copy test")

        source_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/copy-source-{test_id}.txt"
        dest_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/copy-dest-{test_id}.txt"

        try:
            # Upload source
            gcs_adapter.upload_file(str(local_file), source_uri)

            # Copy
            result = gcs_adapter.copy_file(source_uri, dest_uri)
            assert result == dest_uri

            # Verify both exist
            assert gcs_adapter.check_exists(source_uri) is True
            assert gcs_adapter.check_exists(dest_uri) is True
            print(f"✅ Copied file from {source_uri} to {dest_uri}")

        finally:
            # Cleanup
            gcs_adapter.delete_file(source_uri)
            gcs_adapter.delete_file(dest_uri)
            print("✅ Cleaned up test files")

    def test_move_file(self, gcs_adapter, tmp_path):
        """Test moving a file within GCS (copy + delete source)."""
        test_id = str(uuid4())[:8]

        # Create source file
        local_file = tmp_path / f"test-move-source-{test_id}.txt"
        local_file.write_text("Source content for move test")

        source_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/move-source-{test_id}.txt"
        dest_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/move-dest-{test_id}.txt"

        try:
            # Upload source
            gcs_adapter.upload_file(str(local_file), source_uri)

            # Move
            result = gcs_adapter.move_file(source_uri, dest_uri)
            assert result == dest_uri

            # Verify source is gone, dest exists
            assert gcs_adapter.check_exists(source_uri) is False
            assert gcs_adapter.check_exists(dest_uri) is True
            print(f"✅ Moved file from {source_uri} to {dest_uri}")

        finally:
            # Cleanup
            gcs_adapter.delete_file(dest_uri)
            print("✅ Cleaned up test files")

    def test_download_file(self, gcs_adapter, tmp_path):
        """Test downloading a file from GCS to local filesystem."""
        test_id = str(uuid4())[:8]

        # Upload a test file first
        local_upload = tmp_path / f"test-download-upload-{test_id}.txt"
        content = f"Download test content {test_id}"
        local_upload.write_text(content)

        gcs_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/download-test-{test_id}.txt"
        local_download = tmp_path / f"test-download-result-{test_id}.txt"

        try:
            # Upload
            gcs_adapter.upload_file(str(local_upload), gcs_uri)

            # Download
            result = gcs_adapter.download_file(gcs_uri, str(local_download))
            assert result == str(local_download)

            # Verify content
            assert local_download.read_text() == content
            print(f"✅ Downloaded file: {gcs_uri}")

        finally:
            # Cleanup
            gcs_adapter.delete_file(gcs_uri)
            print(f"✅ Cleaned up: {gcs_uri}")


class TestIngestionPipelineWithRealGCS:
    """
    End-to-end tests simulating ingestion pipeline with real GCS.

    Tests the full flow:
    1. File uploaded to _landing zone
    2. Ingestion service moves file to raw zone
    3. Status tracked correctly
    """

    @pytest.fixture(autouse=True)
    def setup_credentials(self):
        """Ensure GCP credentials are set."""
        if not setup_gcp_credentials():
            pytest.skip("GCP credentials not found")

    @pytest.fixture
    def gcs_adapter(self):
        """Create a real GCSAdapter instance."""
        from data_ingestion.adapters.gcs_adapter import GCSAdapter

        return GCSAdapter(
            project_id=GCP_PROJECT_ID,
            default_bucket=TEST_BUCKET,
        )

    def test_landing_to_raw_migration(self, gcs_adapter, tmp_path):
        """Test simulating file migration from landing to raw zone."""
        test_id = str(uuid4())[:8]
        tenant_id = "test-tenant"

        # Simulate file in landing zone
        local_file = tmp_path / f"video-{test_id}.mp4"
        local_file.write_bytes(b"fake video content for testing")

        landing_uri = (
            f"gs://{TEST_BUCKET}/{TEST_PREFIX}/_landing/{tenant_id}/video-{test_id}.mp4"
        )
        raw_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/{tenant_id}/raw/2026/02/03/video-{test_id}.mp4"

        try:
            # Upload to landing zone
            gcs_adapter.upload_file(str(local_file), landing_uri)
            assert gcs_adapter.check_exists(landing_uri) is True
            print(f"✅ Uploaded to landing: {landing_uri}")

            # Get metadata before move
            metadata = gcs_adapter.get_metadata(landing_uri)
            assert metadata.size_bytes > 0
            print(f"   File size: {metadata.size_bytes} bytes")

            # Move to raw zone (simulating ingestion)
            gcs_adapter.move_file(landing_uri, raw_uri)

            # Verify file moved correctly
            assert gcs_adapter.check_exists(landing_uri) is False
            assert gcs_adapter.check_exists(raw_uri) is True
            print(f"✅ Moved to raw zone: {raw_uri}")

            # Verify metadata preserved
            raw_metadata = gcs_adapter.get_metadata(raw_uri)
            assert raw_metadata.size_bytes == metadata.size_bytes
            print("✅ Metadata preserved after move")

        finally:
            # Cleanup
            gcs_adapter.delete_file(landing_uri)
            gcs_adapter.delete_file(raw_uri)
            print("✅ Cleaned up test files")

    def test_batch_file_listing(self, gcs_adapter, tmp_path):
        """Test listing multiple files in a simulated tenant folder."""
        test_id = str(uuid4())[:8]
        tenant_id = f"batch-test-{test_id}"
        file_count = 3

        uploaded_files = []

        try:
            # Upload multiple files
            for i in range(file_count):
                local_file = tmp_path / f"file-{i}.txt"
                local_file.write_text(f"Content {i}")

                gcs_uri = f"gs://{TEST_BUCKET}/{TEST_PREFIX}/{tenant_id}/file-{i}.txt"
                gcs_adapter.upload_file(str(local_file), gcs_uri)
                uploaded_files.append(gcs_uri)

            print(f"✅ Uploaded {file_count} files")

            # List files
            files = gcs_adapter.list_files(
                f"{TEST_PREFIX}/{tenant_id}/",
                bucket_name=TEST_BUCKET,
            )

            assert len(files) == file_count
            print(f"✅ Listed {len(files)} files correctly")

        finally:
            # Cleanup
            for uri in uploaded_files:
                gcs_adapter.delete_file(uri)
            print(f"✅ Cleaned up {len(uploaded_files)} test files")


# =============================================================================
# Pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "gcp: marks tests as requiring Google Cloud Platform credentials",
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require external services)",
    )
