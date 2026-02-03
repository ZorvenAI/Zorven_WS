"""
Unit Tests for RAG Index REST API.

Tests for serializers, views, and URL routing.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from rag_index.api.serializers import (
    BatchSyncRequestSerializer,
    ErrorResponseSerializer,
    RateLimitStatusSerializer,
    SyncEventSerializer,
    SyncResultSerializer,
    SyncStatusRecordSerializer,
)
from rag_index.domain.models import (
    RateLimitStatus,
    SyncAction,
    SyncResult,
    SyncStatus,
    SyncStatusRecord,
)


# API URL prefix
API_PREFIX = "/api/v1/rag-index"


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def api_client():
    """Create an unauthenticated API client."""
    return APIClient()


@pytest.fixture
def authenticated_client(django_user_model):
    """Create an authenticated API client."""
    user = django_user_model.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def sample_sync_event_data():
    """Create sample sync event data."""
    return {
        "tenant_id": "tenant-123",
        "file_id": "file-456",
        "action": "UPSERT",
        "gcs_uri": "gs://bucket/path/doc.json",
    }


@pytest.fixture
def sample_sync_result():
    """Create a sample SyncResult."""
    return SyncResult(
        event_id=uuid.uuid4(),
        trace_id="trace-123",
        status="COMPLETED",
        operation_id="op-123",
        processing_time_ms=150,
    )


@pytest.fixture
def sample_status_record():
    """Create a sample SyncStatusRecord."""
    now = datetime.now(timezone.utc)
    return SyncStatusRecord(
        event_id=uuid.uuid4(),
        trace_id="trace-123",
        tenant_id="tenant-123",
        file_id="file-456",
        action=SyncAction.UPSERT,
        status=SyncStatus.IN_PROGRESS,
        last_updated=now,
    )


@pytest.fixture
def sample_rate_limit_status():
    """Create a sample RateLimitStatus."""
    return RateLimitStatus(
        current_count=50,
        limit=600,
        window_seconds=60,
        remaining=550,
        reset_at=datetime.now(timezone.utc),
    )


# ============================================================================
# SyncEventSerializer Tests
# ============================================================================


class TestSyncEventSerializer:
    """Tests for SyncEventSerializer."""

    def test_valid_upsert_event(self, sample_sync_event_data):
        """Test serializing valid UPSERT event."""
        serializer = SyncEventSerializer(data=sample_sync_event_data)
        assert serializer.is_valid(), serializer.errors
        data = serializer.validated_data
        assert data["tenant_id"] == "tenant-123"
        assert data["action"] == "UPSERT"

    def test_valid_delete_event(self):
        """Test serializing valid DELETE event."""
        data = {
            "tenant_id": "tenant-123",
            "file_id": "file-456",
            "action": "DELETE",
        }
        serializer = SyncEventSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_upsert_without_gcs_uri_fails(self):
        """Test UPSERT without gcs_uri fails validation."""
        data = {
            "tenant_id": "tenant-123",
            "file_id": "file-456",
            "action": "UPSERT",
        }
        serializer = SyncEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "gcs_uri" in serializer.errors

    def test_invalid_gcs_uri_fails(self):
        """Test invalid GCS URI fails validation."""
        data = {
            "tenant_id": "tenant-123",
            "file_id": "file-456",
            "action": "UPSERT",
            "gcs_uri": "https://wrong-scheme/path",
        }
        serializer = SyncEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "gcs_uri" in serializer.errors

    def test_missing_tenant_id_fails(self):
        """Test missing tenant_id fails validation."""
        data = {
            "file_id": "file-456",
            "action": "UPSERT",
            "gcs_uri": "gs://bucket/path/doc.json",
        }
        serializer = SyncEventSerializer(data=data)
        assert not serializer.is_valid()
        assert "tenant_id" in serializer.errors

    def test_optional_fields(self, sample_sync_event_data):
        """Test optional fields have defaults."""
        serializer = SyncEventSerializer(data=sample_sync_event_data)
        assert serializer.is_valid()
        data = serializer.validated_data
        assert data.get("priority", 0) == 0
        assert data.get("metadata", {}) == {}


class TestSyncResultSerializer:
    """Tests for SyncResultSerializer."""

    def test_from_sync_result(self, sample_sync_result):
        """Test converting SyncResult to serialized data."""
        data = SyncResultSerializer.from_sync_result(sample_sync_result)
        assert data["status"] == "COMPLETED"
        assert data["processing_time_ms"] == 150
        assert data["operation_id"] == "op-123"


class TestSyncStatusRecordSerializer:
    """Tests for SyncStatusRecordSerializer."""

    def test_from_status_record(self, sample_status_record):
        """Test converting SyncStatusRecord to serialized data."""
        data = SyncStatusRecordSerializer.from_status_record(sample_status_record)
        assert data["tenant_id"] == "tenant-123"
        assert data["file_id"] == "file-456"
        assert data["status"] == "IN_PROGRESS"
        assert data["retry_count"] == 0


class TestRateLimitStatusSerializer:
    """Tests for RateLimitStatusSerializer."""

    def test_from_rate_limit_status(self, sample_rate_limit_status):
        """Test converting RateLimitStatus to serialized data."""
        data = RateLimitStatusSerializer.from_rate_limit_status(
            sample_rate_limit_status
        )
        assert data["current_count"] == 50
        assert data["limit"] == 600
        assert data["remaining"] == 550
        assert data["is_limited"] is False


class TestBatchSyncRequestSerializer:
    """Tests for BatchSyncRequestSerializer."""

    def test_valid_batch_request(self, sample_sync_event_data):
        """Test valid batch request."""
        data = {
            "events": [sample_sync_event_data, sample_sync_event_data],
            "stop_on_error": False,
        }
        serializer = BatchSyncRequestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert len(serializer.validated_data["events"]) == 2

    def test_batch_size_limit(self, sample_sync_event_data):
        """Test batch size exceeds limit."""
        data = {
            "events": [sample_sync_event_data] * 101,  # Exceeds 100 limit
        }
        serializer = BatchSyncRequestSerializer(data=data)
        assert not serializer.is_valid()
        assert "events" in serializer.errors


# ============================================================================
# HealthViewSet Tests
# ============================================================================


@pytest.mark.django_db
class TestHealthViewSet:
    """Tests for HealthViewSet."""

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_health_endpoint_healthy(
        self, mock_run_async, mock_get_orchestrator, api_client
    ):
        """Test health endpoint returns healthy status."""
        mock_run_async.return_value = {
            "vertex_ai": True,
            "redis": True,
            "gcs": True,
        }

        response = api_client.get(f"{API_PREFIX}/health/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert "version" in response.data
        assert "components" in response.data

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_health_endpoint_degraded(
        self, mock_run_async, mock_get_orchestrator, api_client
    ):
        """Test health endpoint returns degraded status."""
        mock_run_async.return_value = {
            "vertex_ai": True,
            "redis": False,
        }

        response = api_client.get(f"{API_PREFIX}/health/")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["status"] == "degraded"

    def test_live_endpoint(self, api_client):
        """Test liveness probe endpoint."""
        response = api_client.get(f"{API_PREFIX}/health/live/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["alive"] is True

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_ready_endpoint_healthy(
        self, mock_run_async, mock_get_orchestrator, api_client
    ):
        """Test readiness probe when healthy."""
        mock_run_async.return_value = {
            "vertex_ai": True,
        }

        response = api_client.get(f"{API_PREFIX}/health/ready/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["ready"] is True

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_ready_endpoint_unhealthy(
        self, mock_run_async, mock_get_orchestrator, api_client
    ):
        """Test readiness probe when unhealthy."""
        mock_run_async.return_value = {
            "vertex_ai": False,
        }

        response = api_client.get(f"{API_PREFIX}/health/ready/")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert response.data["ready"] is False


# ============================================================================
# SyncStatusViewSet Tests
# ============================================================================


@pytest.mark.django_db
class TestSyncStatusViewSet:
    """Tests for SyncStatusViewSet."""

    def test_get_status_unauthenticated(self, api_client):
        """Test status endpoint requires authentication."""
        event_id = str(uuid.uuid4())
        response = api_client.get(f"{API_PREFIX}/sync/status/{event_id}/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_get_status_found(
        self,
        mock_run_async,
        mock_get_orchestrator,
        authenticated_client,
        sample_status_record,
    ):
        """Test getting existing status."""
        event_id = str(sample_status_record.event_id)
        mock_run_async.return_value = sample_status_record

        response = authenticated_client.get(f"{API_PREFIX}/sync/status/{event_id}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["tenant_id"] == "tenant-123"

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_get_status_not_found(
        self, mock_run_async, mock_get_orchestrator, authenticated_client
    ):
        """Test getting non-existent status."""
        event_id = str(uuid.uuid4())
        mock_run_async.return_value = None

        response = authenticated_client.get(f"{API_PREFIX}/sync/status/{event_id}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"] == "not_found"

    def test_get_status_invalid_id(self, authenticated_client):
        """Test getting status with invalid event ID."""
        response = authenticated_client.get(f"{API_PREFIX}/sync/status/invalid-id/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "invalid_event_id"


# ============================================================================
# SyncTriggerViewSet Tests
# ============================================================================


@pytest.mark.django_db
class TestSyncTriggerViewSet:
    """Tests for SyncTriggerViewSet."""

    def test_create_sync_unauthenticated(self, api_client, sample_sync_event_data):
        """Test sync endpoint requires authentication."""
        response = api_client.post(
            f"{API_PREFIX}/sync/",
            sample_sync_event_data,
            format="json",
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("rag_index.api.views.sync_document")
    def test_create_sync_success(
        self, mock_sync_document, authenticated_client, sample_sync_event_data
    ):
        """Test triggering sync successfully."""
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_sync_document.delay.return_value = mock_task

        response = authenticated_client.post(
            f"{API_PREFIX}/sync/",
            sample_sync_event_data,
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["task_id"] == "task-123"
        assert response.data["status"] == "dispatched"

    def test_create_sync_validation_error(self, authenticated_client):
        """Test sync with invalid data."""
        invalid_data = {
            "tenant_id": "tenant-123",
            # Missing required fields
        }

        response = authenticated_client.post(
            f"{API_PREFIX}/sync/",
            invalid_data,
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "validation_error"

    @patch("rag_index.api.views.batch_sync_documents")
    def test_batch_sync_success(
        self, mock_batch_sync, authenticated_client, sample_sync_event_data
    ):
        """Test batch sync successfully."""
        mock_task = MagicMock()
        mock_task.id = "batch-task-123"
        mock_batch_sync.delay.return_value = mock_task

        response = authenticated_client.post(
            f"{API_PREFIX}/sync/batch/",
            {
                "events": [sample_sync_event_data, sample_sync_event_data],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data["task_id"] == "batch-task-123"
        assert response.data["batch_size"] == 2


# ============================================================================
# RateLimitViewSet Tests
# ============================================================================


@pytest.mark.django_db
class TestRateLimitViewSet:
    """Tests for RateLimitViewSet."""

    def test_rate_limit_unauthenticated(self, api_client):
        """Test rate limit endpoint requires authentication."""
        response = api_client.get(f"{API_PREFIX}/rate-limit/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_rate_limit_status(
        self,
        mock_run_async,
        mock_get_orchestrator,
        authenticated_client,
        sample_rate_limit_status,
    ):
        """Test getting rate limit status."""
        mock_run_async.return_value = sample_rate_limit_status

        response = authenticated_client.get(f"{API_PREFIX}/rate-limit/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["limit"] == 600
        assert response.data["current_count"] == 50

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_rate_limit_not_configured(
        self, mock_run_async, mock_get_orchestrator, authenticated_client
    ):
        """Test rate limit when not configured."""
        mock_run_async.return_value = None

        response = authenticated_client.get(f"{API_PREFIX}/rate-limit/")

        assert response.status_code == status.HTTP_200_OK
        assert "not configured" in response.data["message"]


# ============================================================================
# URL Routing Tests
# ============================================================================


@pytest.mark.django_db
class TestURLRouting:
    """Tests for URL routing."""

    def test_health_url_exists(self, api_client):
        """Test health URL is accessible."""
        response = api_client.get(f"{API_PREFIX}/health/live/")
        assert response.status_code == status.HTTP_200_OK

    @patch("rag_index.api.views.sync_document")
    def test_sync_url_exists(
        self, mock_sync, authenticated_client, sample_sync_event_data
    ):
        """Test sync URL is accessible."""
        mock_sync.delay.return_value = MagicMock(id="task-123")
        response = authenticated_client.post(
            f"{API_PREFIX}/sync/",
            sample_sync_event_data,
            format="json",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED

    @patch("rag_index.api.views.get_orchestrator")
    @patch("rag_index.api.views.run_async")
    def test_status_url_exists(
        self, mock_run_async, mock_get_orchestrator, authenticated_client
    ):
        """Test status URL is accessible."""
        event_id = str(uuid.uuid4())
        mock_run_async.return_value = None
        response = authenticated_client.get(f"{API_PREFIX}/sync/status/{event_id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Error Response Tests
# ============================================================================


class TestErrorResponses:
    """Tests for error response format."""

    def test_error_response_serializer(self):
        """Test error response serializer."""
        data = {
            "error": "validation_error",
            "message": "Invalid data",
            "details": {"field": "error"},
            "trace_id": "trace-123",
        }
        serializer = ErrorResponseSerializer(data=data)
        assert serializer.is_valid()


# ============================================================================
# Trace ID Tests
# ============================================================================


@pytest.mark.django_db
class TestTraceID:
    """Tests for trace ID handling."""

    def test_trace_id_from_header(self, api_client):
        """Test trace ID is extracted from header."""
        response = api_client.get(
            f"{API_PREFIX}/health/live/",
            HTTP_X_TRACE_ID="custom-trace-123",
        )
        assert response.status_code == status.HTTP_200_OK

    @patch("rag_index.api.views.sync_document")
    def test_trace_id_in_response(
        self, mock_sync, authenticated_client, sample_sync_event_data
    ):
        """Test trace ID propagates to task."""
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_sync.delay.return_value = mock_task

        response = authenticated_client.post(
            f"{API_PREFIX}/sync/",
            sample_sync_event_data,
            format="json",
            HTTP_X_TRACE_ID="custom-trace-456",
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        # Verify delay was called with trace_id in event
        call_args = mock_sync.delay.call_args[0][0]
        assert call_args["trace_id"] == "custom-trace-456"
