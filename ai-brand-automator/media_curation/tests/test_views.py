"""
Tests for Media Curation API endpoints.

Tests the REST API views for curation operations.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4, UUID

from rest_framework import status


# Sample UUIDs for testing
SAMPLE_TENANT_ID = "11111111-1111-1111-1111-111111111111"
SAMPLE_TRACE_ID = "22222222-2222-2222-2222-222222222222"


# api_client and authenticated_client fixtures come from the global
# conftest.py — they use real Django User instances which is required
# by TenantMembershipMiddleware (MagicMock users cause DB query errors).


class TestCurationEndpoint:
    """Tests for POST /curation/ endpoint."""

    @pytest.mark.django_db
    def test_submit_curation_request_success(self, authenticated_client):
        """Test successful curation request submission."""
        with patch("media_curation.tasks.process_curation_event") as mock_task:
            mock_task.delay = MagicMock()

            response = authenticated_client.post(
                "/api/v1/curation/",
                data={
                    "tenant_id": SAMPLE_TENANT_ID,
                    "source_path": "gs://test-bucket/file.pdf",
                    "file_type": "application/pdf",
                },
                format="json",
            )

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert "event_id" in data
            assert "trace_id" in data
            assert data["status"] == "accepted"
            assert data["message"] == "Curation request queued for processing"

    @pytest.mark.django_db
    def test_submit_curation_request_calls_celery(self, authenticated_client):
        """Test that Celery task is called with correct args."""
        with patch("media_curation.tasks.process_curation_event") as mock_task:
            mock_task.delay = MagicMock()

            authenticated_client.post(
                "/api/v1/curation/",
                data={
                    "tenant_id": SAMPLE_TENANT_ID,
                    "source_path": "gs://test-bucket/file.pdf",
                    "file_type": "application/pdf",
                    "file_size_bytes": 1024,
                    "metadata": {"key": "value"},
                },
                format="json",
            )

            mock_task.delay.assert_called_once()
            call_kwargs = mock_task.delay.call_args.kwargs
            assert call_kwargs["tenant_id"] == SAMPLE_TENANT_ID
            assert call_kwargs["source_path"] == "gs://test-bucket/file.pdf"
            assert call_kwargs["file_type"] == "application/pdf"
            assert call_kwargs["file_size_bytes"] == 1024
            assert call_kwargs["metadata"] == {"key": "value"}

    @pytest.mark.django_db
    def test_submit_curation_request_invalid_source_path(self, authenticated_client):
        """Test validation error for invalid source path."""
        response = authenticated_client.post(
            "/api/v1/curation/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "source_path": "/local/path/file.pdf",  # Not a GCS URI
                "file_type": "application/pdf",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "source_path" in response.json()

    @pytest.mark.django_db
    def test_submit_curation_request_missing_required_fields(
        self, authenticated_client
    ):
        """Test validation error for missing required fields."""
        response = authenticated_client.post(
            "/api/v1/curation/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                # Missing source_path and file_type
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_submit_curation_request_unauthenticated(self, api_client):
        """Test that unauthenticated requests are rejected."""
        response = api_client.post(
            "/api/v1/curation/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "source_path": "gs://test-bucket/file.pdf",
                "file_type": "application/pdf",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestBatchCurationEndpoint:
    """Tests for POST /curation/batch/ endpoint."""

    @pytest.mark.django_db
    def test_batch_curation_request_success(self, authenticated_client):
        """Test successful batch curation request."""
        with patch("media_curation.tasks.process_curation_event") as mock_task:
            mock_task.delay = MagicMock()

            response = authenticated_client.post(
                "/api/v1/curation/batch/",
                data={
                    "events": [
                        {
                            "tenant_id": SAMPLE_TENANT_ID,
                            "source_path": "gs://test-bucket/file1.pdf",
                            "file_type": "application/pdf",
                        },
                        {
                            "tenant_id": SAMPLE_TENANT_ID,
                            "source_path": "gs://test-bucket/file2.pdf",
                            "file_type": "application/pdf",
                        },
                    ]
                },
                format="json",
            )

            assert response.status_code == status.HTTP_202_ACCEPTED
            data = response.json()
            assert data["accepted"] == 2
            assert data["rejected"] == 0
            assert len(data["results"]) == 2
            assert mock_task.delay.call_count == 2

    @pytest.mark.django_db
    def test_batch_curation_empty_events(self, authenticated_client):
        """Test validation error for empty batch."""
        response = authenticated_client.post(
            "/api/v1/curation/batch/",
            data={"events": []},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_batch_curation_exceeds_max_size(self, authenticated_client):
        """Test validation error when batch exceeds max size."""
        events = [
            {
                "tenant_id": SAMPLE_TENANT_ID,
                "source_path": f"gs://test-bucket/file{i}.pdf",
                "file_type": "application/pdf",
            }
            for i in range(101)  # Max is 100
        ]

        response = authenticated_client.post(
            "/api/v1/curation/batch/",
            data={"events": events},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestStatusEndpoint:
    """Tests for GET /curation/status/{trace_id}/ endpoint."""

    @pytest.mark.django_db
    def test_get_status_found(self, authenticated_client):
        """Test getting status for existing trace_id."""
        from media_curation.domain.models import CurationStatusRecord, CurationStatus

        mock_status = CurationStatusRecord(
            trace_id=UUID(SAMPLE_TRACE_ID),
            event_id=uuid4(),
            tenant_id=SAMPLE_TENANT_ID,
            file_id=uuid4(),
            status=CurationStatus.CURATED,
            message="Success",
            output_gcs_uri="gs://curated-bucket/output.json",
            updated_at=datetime.now(timezone.utc),
        )

        with patch("media_curation.factory.create_cache_adapter") as mock_cache_factory:
            mock_cache = MagicMock()
            mock_cache.get_status = AsyncMock(return_value=mock_status)
            mock_cache_factory.return_value = mock_cache

            response = authenticated_client.get(
                f"/api/v1/curation/status/{SAMPLE_TRACE_ID}/"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["trace_id"] == SAMPLE_TRACE_ID
            assert data["status"] == "curated"
            assert data["destination_path"] == "gs://curated-bucket/output.json"

    @pytest.mark.django_db
    def test_get_status_not_found(self, authenticated_client):
        """Test getting status for non-existent trace_id."""
        with patch("media_curation.factory.create_cache_adapter") as mock_cache_factory:
            mock_cache = MagicMock()
            mock_cache.get_status = AsyncMock(return_value=None)
            mock_cache_factory.return_value = mock_cache

            response = authenticated_client.get(
                f"/api/v1/curation/status/{SAMPLE_TRACE_ID}/"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "NOT_FOUND"


class TestHealthEndpoint:
    """Tests for GET /curation/health/ endpoint."""

    @pytest.mark.django_db
    def test_health_check_all_healthy(self, api_client):
        """Test health check when all components are healthy."""
        with patch(
            "media_curation.factory.create_cache_adapter"
        ) as mock_cache_factory, patch(
            "media_curation.factory.create_storage_adapter"
        ) as mock_storage_factory, patch(
            "media_curation.factory.create_kafka_producer"
        ) as mock_kafka_factory:
            # Mock healthy components
            mock_cache = MagicMock()
            mock_cache.is_healthy = AsyncMock(return_value=True)
            mock_cache_factory.return_value = mock_cache

            mock_storage = MagicMock()
            mock_storage.is_healthy = AsyncMock(return_value=True)
            mock_storage_factory.return_value = mock_storage

            mock_kafka = MagicMock()
            mock_kafka._kafka_available = True
            mock_kafka_factory.return_value = mock_kafka

            response = api_client.get("/api/v1/curation/health/")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] in ["healthy", "degraded"]
            assert "components" in data
            assert "redis" in data["components"]
            assert "kafka" in data["components"]
            assert "gcs" in data["components"]

    @pytest.mark.django_db
    def test_health_check_public_endpoint(self, api_client):
        """Test that health check doesn't require authentication."""
        with patch(
            "media_curation.factory.create_cache_adapter"
        ) as mock_cache_factory, patch(
            "media_curation.factory.create_storage_adapter"
        ) as mock_storage_factory, patch(
            "media_curation.factory.create_kafka_producer"
        ) as mock_kafka_factory:
            mock_cache = MagicMock()
            mock_cache.is_healthy = AsyncMock(return_value=True)
            mock_cache_factory.return_value = mock_cache

            mock_storage = MagicMock()
            mock_storage.is_healthy = AsyncMock(return_value=True)
            mock_storage_factory.return_value = mock_storage

            mock_kafka = MagicMock()
            mock_kafka._kafka_available = False
            mock_kafka_factory.return_value = mock_kafka

            # No authentication
            response = api_client.get("/api/v1/curation/health/")

            # Should still work
            assert response.status_code == status.HTTP_200_OK

    @pytest.mark.django_db
    def test_health_check_degraded_when_redis_unhealthy(self, api_client):
        """Test health check returns degraded when Redis is unhealthy."""
        with patch(
            "media_curation.factory.create_cache_adapter"
        ) as mock_cache_factory, patch(
            "media_curation.factory.create_storage_adapter"
        ) as mock_storage_factory, patch(
            "media_curation.factory.create_kafka_producer"
        ) as mock_kafka_factory:
            mock_cache = MagicMock()
            mock_cache.is_healthy = AsyncMock(return_value=False)
            mock_cache_factory.return_value = mock_cache

            mock_storage = MagicMock()
            mock_storage.is_healthy = AsyncMock(return_value=True)
            mock_storage_factory.return_value = mock_storage

            mock_kafka = MagicMock()
            mock_kafka._kafka_available = True
            mock_kafka_factory.return_value = mock_kafka

            response = api_client.get("/api/v1/curation/health/")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "degraded"


class TestSyncEndpoint:
    """Tests for POST /curation/sync/ endpoint."""

    @pytest.mark.django_db
    def test_sync_curation_success(self, authenticated_client):
        """Test successful synchronous curation."""
        from media_curation.domain.models import CurationStatus
        from datetime import datetime, timezone

        mock_doc = MagicMock()
        mock_doc.document_id = uuid4()
        mock_doc.event_id = uuid4()
        mock_doc.trace_id = uuid4()
        mock_doc.tenant_id = SAMPLE_TENANT_ID
        mock_doc.brand_id = None
        mock_doc.source_gcs_uri = "gs://test-bucket/file.pdf"
        mock_doc.curated_gcs_uri = "gs://curated-bucket/output.json"
        mock_doc.content_type = "application/pdf"
        mock_doc.title = "Test Document"
        mock_doc.extracted_text = "Test content"
        mock_doc.summary = "Test summary"
        mock_doc.entities = []
        mock_doc.keywords = ["test"]
        mock_doc.detected_language = "en"
        mock_doc.status = CurationStatus.CURATED
        mock_doc.confidence_score = 0.95
        mock_doc.pii_redacted = False
        mock_doc.pii_findings_count = 0
        mock_doc.created_at = datetime.now(timezone.utc)
        mock_doc.processing_duration_ms = 500
        mock_doc.metadata = {}

        with patch(
            "media_curation.domain.services.CurationService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.process = AsyncMock(return_value=mock_doc)
            mock_service_cls.return_value = mock_service

            response = authenticated_client.post(
                "/api/v1/curation/sync/",
                data={
                    "tenant_id": SAMPLE_TENANT_ID,
                    "source_path": "gs://test-bucket/file.pdf",
                    "file_type": "application/pdf",
                },
                format="json",
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["status"] == "completed"
            assert data["document"] is not None
            assert data["error"] is None

    @pytest.mark.django_db
    def test_sync_curation_invalid_source_path(self, authenticated_client):
        """Test sync curation with invalid source path."""
        response = authenticated_client.post(
            "/api/v1/curation/sync/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "source_path": "/local/path/file.pdf",
                "file_type": "application/pdf",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_sync_curation_service_error(self, authenticated_client):
        """Test sync curation when service raises error."""
        with patch(
            "media_curation.domain.services.CurationService"
        ) as mock_service_cls:
            mock_service = MagicMock()
            mock_service.process = AsyncMock(side_effect=Exception("Processing failed"))
            mock_service_cls.return_value = mock_service

            response = authenticated_client.post(
                "/api/v1/curation/sync/",
                data={
                    "tenant_id": SAMPLE_TENANT_ID,
                    "source_path": "gs://test-bucket/file.pdf",
                    "file_type": "application/pdf",
                },
                format="json",
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert data["status"] == "failed"
            assert "Processing failed" in data["error"]

    @pytest.mark.django_db
    def test_sync_curation_unauthenticated(self, api_client):
        """Test sync curation requires authentication."""
        response = api_client.post(
            "/api/v1/curation/sync/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "source_path": "gs://test-bucket/file.pdf",
                "file_type": "application/pdf",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestTenantConfigEndpoint:
    """Tests for /curation/config/ CRUD endpoints."""

    @pytest.fixture(autouse=True)
    def clear_configs(self):
        """Clear tenant configs between tests."""
        from media_curation.views import TenantConfigViewSet

        TenantConfigViewSet._configs.clear()
        yield
        TenantConfigViewSet._configs.clear()

    @pytest.mark.django_db
    def test_create_tenant_config(self, authenticated_client):
        """Test creating a new tenant config."""
        response = authenticated_client.post(
            "/api/v1/curation/config/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "enabled": True,
                "max_file_size_mb": 50,
                "pii_detection_enabled": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["tenant_id"] == SAMPLE_TENANT_ID
        assert data["enabled"] is True
        assert data["max_file_size_mb"] == 50

    @pytest.mark.django_db
    def test_create_tenant_config_duplicate(self, authenticated_client):
        """Test creating duplicate tenant config returns conflict."""
        # Create first config
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID},
            format="json",
        )

        # Try to create duplicate
        response = authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID},
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.django_db
    def test_get_tenant_config(self, authenticated_client):
        """Test retrieving a tenant config."""
        # Create config first
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID, "max_file_size_mb": 75},
            format="json",
        )

        response = authenticated_client.get(
            f"/api/v1/curation/config/{SAMPLE_TENANT_ID}/"
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["tenant_id"] == SAMPLE_TENANT_ID
        assert data["max_file_size_mb"] == 75

    @pytest.mark.django_db
    def test_get_tenant_config_not_found(self, authenticated_client):
        """Test retrieving non-existent tenant config."""
        response = authenticated_client.get("/api/v1/curation/config/nonexistent/")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_update_tenant_config(self, authenticated_client):
        """Test updating a tenant config."""
        # Create config first
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID, "max_file_size_mb": 50},
            format="json",
        )

        # Update config
        response = authenticated_client.put(
            f"/api/v1/curation/config/{SAMPLE_TENANT_ID}/",
            data={"tenant_id": SAMPLE_TENANT_ID, "max_file_size_mb": 100},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["max_file_size_mb"] == 100

    @pytest.mark.django_db
    def test_update_tenant_config_mismatch(self, authenticated_client):
        """Test updating with mismatched tenant_id."""
        # Create config first
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID},
            format="json",
        )

        # Try to update with different tenant_id in body
        response = authenticated_client.put(
            f"/api/v1/curation/config/{SAMPLE_TENANT_ID}/",
            data={"tenant_id": "different-tenant"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_delete_tenant_config(self, authenticated_client):
        """Test deleting a tenant config."""
        # Create config first
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID},
            format="json",
        )

        response = authenticated_client.delete(
            f"/api/v1/curation/config/{SAMPLE_TENANT_ID}/"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

        # Verify it's gone
        response = authenticated_client.get(
            f"/api/v1/curation/config/{SAMPLE_TENANT_ID}/"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.django_db
    def test_list_tenant_configs(self, authenticated_client):
        """Test listing tenant configs."""
        # Create multiple configs
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": "tenant-1"},
            format="json",
        )
        authenticated_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": "tenant-2"},
            format="json",
        )

        response = authenticated_client.get("/api/v1/curation/config/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2

    @pytest.mark.django_db
    def test_tenant_config_validation_max_file_size(self, authenticated_client):
        """Test validation for max_file_size_mb."""
        response = authenticated_client.post(
            "/api/v1/curation/config/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "max_file_size_mb": 1000,
            },  # Max is 500
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_tenant_config_validation_file_types(self, authenticated_client):
        """Test validation for allowed_file_types."""
        response = authenticated_client.post(
            "/api/v1/curation/config/",
            data={
                "tenant_id": SAMPLE_TENANT_ID,
                "allowed_file_types": ["invalid/type", "xyz"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.django_db
    def test_tenant_config_unauthenticated(self, api_client):
        """Test tenant config endpoints require authentication."""
        response = api_client.get("/api/v1/curation/config/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

        response = api_client.post(
            "/api/v1/curation/config/",
            data={"tenant_id": SAMPLE_TENANT_ID},
            format="json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
