"""
Tests for Data Ingestion REST API endpoints.

Tests the DRF views and serializers for the ingestion microservice.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from data_ingestion.serializers import (
    IngestionEventSerializer,
    BatchIngestionSerializer,
    HealthCheckSerializer,
)
from data_ingestion.domain.models import (
    IngestionEvent,
    ProcessedEvent,
    EventSource,
    ProcessingStatus,
)


@pytest.mark.django_db
class TestIngestionEventSerializer:
    """Tests for IngestionEventSerializer."""

    def test_valid_minimal_data(self):
        """Test serializer accepts minimal required data."""
        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        serializer = IngestionEventSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        validated = serializer.validated_data
        assert validated["tenant_id"] == "customer-1"
        assert validated["file_path"] == "gs://bucket/_landing/file.mp4"

    def test_valid_full_data(self):
        """Test serializer accepts full data."""
        data = {
            "event_id": str(uuid4()),
            "trace_id": str(uuid4()),
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
            "file_type": "video/mp4",
            "file_size_bytes": 1048576,
            "source": "api-integration",  # hyphenated, not underscore
            "metadata": {"original_name": "demo.mp4"},
        }
        serializer = IngestionEventSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        validated = serializer.validated_data
        assert validated["file_type"] == "video/mp4"
        assert validated["file_size_bytes"] == 1048576

    def test_missing_tenant_id(self):
        """Test serializer rejects missing tenant_id."""
        data = {
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        serializer = IngestionEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "tenant_id" in serializer.errors

    def test_missing_file_path(self):
        """Test serializer rejects missing file_path."""
        data = {
            "tenant_id": "customer-1",
        }
        serializer = IngestionEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "file_path" in serializer.errors

    def test_empty_tenant_id(self):
        """Test serializer rejects empty tenant_id."""
        data = {
            "tenant_id": "",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        serializer = IngestionEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "tenant_id" in serializer.errors

    def test_empty_file_path(self):
        """Test serializer rejects empty file_path."""
        data = {
            "tenant_id": "customer-1",
            "file_path": "",
        }
        serializer = IngestionEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "file_path" in serializer.errors

    def test_negative_file_size(self):
        """Test serializer rejects negative file_size_bytes."""
        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
            "file_size_bytes": -100,
        }
        serializer = IngestionEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "file_size_bytes" in serializer.errors

    def test_create_generates_ids(self):
        """Test create() generates event_id and trace_id if not provided."""
        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        serializer = IngestionEventSerializer(data=data)
        assert serializer.is_valid()
        result = serializer.create(serializer.validated_data)
        assert "event_id" in result
        assert "trace_id" in result
        assert result["event_id"] is not None
        assert result["trace_id"] is not None


@pytest.mark.django_db
class TestBatchIngestionSerializer:
    """Tests for BatchIngestionSerializer."""

    def test_valid_batch(self):
        """Test serializer accepts valid batch."""
        data = {
            "events": [
                {
                    "tenant_id": "customer-1",
                    "file_path": "gs://bucket/_landing/file1.mp4",
                },
                {
                    "tenant_id": "customer-1",
                    "file_path": "gs://bucket/_landing/file2.mp4",
                },
            ]
        }
        serializer = BatchIngestionSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert len(serializer.validated_data["events"]) == 2

    def test_empty_batch_rejected(self):
        """Test serializer rejects empty batch."""
        data = {"events": []}
        serializer = BatchIngestionSerializer(data=data)
        assert not serializer.is_valid()
        assert "events" in serializer.errors

    def test_batch_exceeds_max_size(self):
        """Test serializer rejects batch exceeding 100 events."""
        events = [
            {
                "tenant_id": "customer-1",
                "file_path": f"gs://bucket/_landing/file{i}.mp4",
            }
            for i in range(101)
        ]
        data = {"events": events}
        serializer = BatchIngestionSerializer(data=data)
        assert not serializer.is_valid()
        assert "events" in serializer.errors

    def test_single_event_batch(self):
        """Test serializer accepts single event batch."""
        data = {
            "events": [
                {
                    "tenant_id": "customer-1",
                    "file_path": "gs://bucket/_landing/file.mp4",
                }
            ]
        }
        serializer = BatchIngestionSerializer(data=data)
        assert serializer.is_valid()


@pytest.mark.django_db
class TestHealthCheckSerializer:
    """Tests for HealthCheckSerializer."""

    def test_healthy_response(self):
        """Test serializer handles healthy response."""
        data = {
            "status": "healthy",
            "components": {
                "redis": {"status": "healthy"},
                "gcs": {"status": "healthy"},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        serializer = HealthCheckSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_degraded_response(self):
        """Test serializer handles degraded response."""
        data = {
            "status": "degraded",
            "components": {
                "redis": {"status": "unhealthy", "error": "Connection refused"},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        serializer = HealthCheckSerializer(data=data)
        assert serializer.is_valid()


@pytest.mark.django_db
class TestIngestionAPIEndpoints:
    """Tests for the ingestion REST API endpoints."""

    @pytest.fixture
    def api_client(self):
        """Create API client."""
        client = APIClient()
        client.defaults["SERVER_NAME"] = "localhost"
        return client

    @pytest.fixture
    def authenticated_client(self, api_client):
        """Create authenticated API client."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(
            email="test@example.com", username="testuser", password="testpass123"
        )
        api_client.force_authenticate(user=user)
        return api_client

    def test_health_endpoint_public(self, api_client):
        """Test health endpoint is accessible without auth."""
        with patch("data_ingestion.views.create_redis_adapter") as mock_redis:
            mock_adapter = MagicMock()
            mock_adapter.health_check.return_value = True
            mock_redis.return_value = mock_adapter

            with patch("data_ingestion.views.create_gcs_adapter"):
                with patch(
                    "data_ingestion.views.get_data_ingestion_config"
                ) as mock_config:
                    mock_config.return_value = {"bucket": "test"}

                    response = api_client.get("/api/v1/ingestion/health/")
                    assert response.status_code == status.HTTP_200_OK
                    data = response.json()
                    assert data["status"] == "healthy"
                    assert "components" in data
                    assert "timestamp" in data

    def test_ingest_requires_auth(self, api_client):
        """Test ingest endpoint requires authentication."""
        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        response = api_client.post(
            "/api/v1/ingestion/",
            data=json.dumps(data),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("data_ingestion.views.process_ingestion_event")
    def test_ingest_single_event(self, mock_task, authenticated_client):
        """Test submitting single ingestion event."""
        mock_task.delay.return_value = MagicMock(id="task-123")

        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
            "file_type": "video/mp4",
        }
        response = authenticated_client.post(
            "/api/v1/ingestion/",
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        response_data = response.json()
        assert response_data["status"] == "accepted"
        assert "event_id" in response_data
        assert "trace_id" in response_data
        assert response_data["task_id"] == "task-123"
        mock_task.delay.assert_called_once()

    def test_ingest_validation_error(self, authenticated_client):
        """Test ingest endpoint returns validation errors."""
        data = {
            "file_path": "gs://bucket/_landing/file.mp4",
            # Missing tenant_id
        }
        response = authenticated_client.post(
            "/api/v1/ingestion/",
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        response_data = response.json()
        assert response_data["status"] == "failed"
        assert "error" in response_data

    @patch("data_ingestion.views.process_batch")
    def test_batch_ingest(self, mock_task, authenticated_client):
        """Test submitting batch ingestion."""
        mock_task.delay.return_value = MagicMock(id="batch-task-123")

        data = {
            "events": [
                {
                    "tenant_id": "customer-1",
                    "file_path": "gs://bucket/_landing/file1.mp4",
                },
                {
                    "tenant_id": "customer-1",
                    "file_path": "gs://bucket/_landing/file2.mp4",
                },
            ]
        }
        response = authenticated_client.post(
            "/api/v1/ingestion/batch/",
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        response_data = response.json()
        assert response_data["status"] == "accepted"
        assert response_data["accepted"] == 2
        assert response_data["rejected"] == 0
        mock_task.delay.assert_called_once()

    @patch("data_ingestion.views.process_batch")
    def test_batch_partial_rejection(self, mock_task, authenticated_client):
        """Test batch with some invalid events."""
        mock_task.delay.return_value = MagicMock(id="batch-task-123")

        data = {
            "events": [
                {
                    "tenant_id": "customer-1",
                    "file_path": "gs://bucket/_landing/file1.mp4",
                },
                {
                    "file_path": "gs://bucket/_landing/file2.mp4",
                    # Missing tenant_id
                },
            ]
        }
        response = authenticated_client.post(
            "/api/v1/ingestion/batch/",
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        response_data = response.json()
        assert response_data["status"] == "partial"
        assert response_data["accepted"] == 1
        assert response_data["rejected"] == 1

    @patch("data_ingestion.views.create_redis_adapter")
    def test_status_endpoint(self, mock_redis, authenticated_client):
        """Test checking ingestion status."""
        mock_adapter = MagicMock()
        mock_adapter.get_status.return_value = {
            "status": "completed",
            "updated_at": "2026-01-29T10:00:00Z",
            "metadata": {"destination": "gs://bucket/_raw/file.mp4"},
        }
        mock_redis.return_value = mock_adapter

        trace_id = str(uuid4())
        response = authenticated_client.get(f"/api/v1/ingestion/status/{trace_id}/")

        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert response_data["trace_id"] == trace_id
        assert response_data["status"] == "completed"

    @patch("data_ingestion.views.create_redis_adapter")
    def test_status_not_found(self, mock_redis, authenticated_client):
        """Test status for unknown trace_id."""
        mock_adapter = MagicMock()
        mock_adapter.get_status.return_value = None
        mock_redis.return_value = mock_adapter

        trace_id = str(uuid4())
        response = authenticated_client.get(f"/api/v1/ingestion/status/{trace_id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        response_data = response.json()
        assert response_data["status"] == "not_found"

    @patch("data_ingestion.views.create_ingestion_service")
    def test_sync_processing(self, mock_service, authenticated_client):
        """Test synchronous processing endpoint."""
        mock_result = ProcessedEvent(
            event_id=uuid4(),
            trace_id=uuid4(),
            tenant_id="customer-1",
            source_path="gs://bucket/_landing/file.mp4",
            destination_path="gs://bucket/_raw/customer-1/file.mp4",
            status=ProcessingStatus.RAW_STORED,
            processing_duration_ms=150,
        )
        mock_svc = MagicMock()
        mock_svc.process_event.return_value = mock_result
        mock_service.return_value = mock_svc

        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        response = authenticated_client.post(
            "/api/v1/ingestion/sync/",
            data=json.dumps(data),
            content_type="application/json",
        )

        assert response.status_code == status.HTTP_200_OK
        response_data = response.json()
        assert response_data["status"] == "success"
        assert "destination_path" in response_data

    def test_health_degraded_when_redis_fails(self, api_client):
        """Test health returns degraded when Redis fails."""
        with patch("data_ingestion.views.create_redis_adapter") as mock_redis:
            mock_redis.side_effect = Exception("Connection refused")

            with patch("data_ingestion.views.create_gcs_adapter"):
                with patch(
                    "data_ingestion.views.get_data_ingestion_config"
                ) as mock_config:
                    mock_config.return_value = {"bucket": "test"}

                    response = api_client.get("/api/v1/ingestion/health/")
                    # Should return 503 when degraded
                    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                    data = response.json()
                    assert data["status"] == "degraded"


@pytest.mark.django_db
class TestIngestionSerializerCreateMethod:
    """Test serializer create method properly generates IDs."""

    def test_create_preserves_provided_ids(self):
        """Test create() preserves IDs when provided."""
        event_id = uuid4()
        trace_id = uuid4()
        data = {
            "event_id": str(event_id),
            "trace_id": str(trace_id),
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        serializer = IngestionEventSerializer(data=data)
        assert serializer.is_valid()
        result = serializer.create(serializer.validated_data)
        assert str(result["event_id"]) == str(event_id)
        assert str(result["trace_id"]) == str(trace_id)

    def test_create_sets_default_timestamp(self):
        """Test create() sets timestamp if not provided."""
        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
        }
        serializer = IngestionEventSerializer(data=data)
        assert serializer.is_valid()
        result = serializer.create(serializer.validated_data)
        assert "timestamp" in result
        assert result["timestamp"] is not None

    def test_create_preserves_provided_timestamp(self):
        """Test create() preserves timestamp when provided."""
        timestamp = datetime(2026, 1, 29, 10, 0, 0)
        data = {
            "tenant_id": "customer-1",
            "file_path": "gs://bucket/_landing/file.mp4",
            "timestamp": timestamp.isoformat(),
        }
        serializer = IngestionEventSerializer(data=data)
        assert serializer.is_valid()
        result = serializer.create(serializer.validated_data)
        # Compare just the datetime part (timezone may differ)
        assert result["timestamp"].year == 2026
        assert result["timestamp"].month == 1
        assert result["timestamp"].day == 29
