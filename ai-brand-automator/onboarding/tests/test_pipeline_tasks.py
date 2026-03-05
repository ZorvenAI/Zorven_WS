"""
Unit tests for onboarding Celery tasks.

Tests cover:
- export_company_for_rag task (delegates to sync_model_to_rag)
- batch_export_companies_for_rag task
- Company document building (via DbSyncService)
- process_asset_pipeline_sync task (3-stage pipeline)
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from onboarding.models import Company
from onboarding.tasks import (
    export_company_for_rag,
    batch_export_companies_for_rag,
    process_asset_pipeline_sync,
    _run_indexing,
)
from rag_index.services.db_sync_service import DbSyncService


@pytest.fixture
def sample_company_for_task(db, public_tenant):
    """Create a sample company for testing (unique per test)."""
    # Delete any existing company for this tenant first
    Company.objects.filter(tenant=public_tenant).delete()

    return Company.objects.create(
        tenant=public_tenant,
        name="Test Export Company",
        description="A company for testing exports",
        industry="Technology",
        target_audience="Developers",
        values="Innovation, Quality",
        brand_voice="professional",
    )


class TestBuildCompanyDocument:
    """Tests for Company document builder (via DbSyncService)."""

    def test_builds_document_with_all_fields(self, sample_company_for_task):
        """Should build document with all company fields."""
        doc = DbSyncService().build_document("Company", sample_company_for_task)

        assert doc["document_type"] == "company_profile"
        assert doc["metadata"]["company_id"] == str(sample_company_for_task.id)
        assert "Test Export Company" in doc["extracted_text"]
        assert "Technology" in doc["extracted_text"]
        assert "Developers" in doc["extracted_text"]
        assert "Innovation" in doc["extracted_text"]

    def test_builds_document_with_metadata(self, sample_company_for_task):
        """Should include name and industry in metadata."""
        doc = DbSyncService().build_document("Company", sample_company_for_task)

        assert doc["metadata"]["name"] == "Test Export Company"
        assert doc["metadata"]["industry"] == "Technology"

    def test_handles_empty_optional_fields(self, db, public_tenant):
        """Should handle companies with minimal data."""
        Company.objects.filter(tenant=public_tenant).delete()

        company = Company.objects.create(
            tenant=public_tenant,
            name="Minimal Company",
        )

        doc = DbSyncService().build_document("Company", company)

        assert doc["document_type"] == "company_profile"
        assert "Minimal Company" in doc["extracted_text"]

    def test_includes_asset_count(self, sample_company_for_task, public_tenant):
        """Should include brand asset count in extracted text."""
        from onboarding.models import BrandAsset

        for i in range(3):
            BrandAsset.objects.create(
                tenant=public_tenant,
                company=sample_company_for_task,
                file_name=f"asset_{i}.jpg",
                file_type="image",
                file_size=1024,
                gcs_path=f"_landing/1/asset_{i}.jpg",
            )

        doc = DbSyncService().build_document("Company", sample_company_for_task)

        assert "3 files uploaded" in doc["extracted_text"]


class TestExportCompanyForRag:
    """Tests for export_company_for_rag Celery task (delegates to sync_model_to_rag)."""

    @pytest.mark.django_db
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_export_delegates_to_sync_model(
        self, mock_sync_task, sample_company_for_task
    ):
        """Should delegate to sync_model_to_rag task."""
        result = export_company_for_rag(sample_company_for_task.id)

        assert result["status"] == "delegated"
        assert result["company_id"] == sample_company_for_task.id
        mock_sync_task.apply_async.assert_called_once_with(
            args=[
                "Company",
                sample_company_for_task.id,
                str(sample_company_for_task.tenant.id),
            ],
        )

    @pytest.mark.django_db
    def test_export_company_not_found(self):
        """Should return error for non-existent company."""
        result = export_company_for_rag(99999)

        assert result["status"] == "error"
        assert "not found" in result["message"]


class TestBatchExportCompaniesForRag:
    """Tests for batch_export_companies_for_rag Celery task."""

    @pytest.mark.django_db
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_batch_export_all_companies(self, mock_sync_task, db, public_tenant):
        """Should queue sync_model_to_rag for all companies."""
        Company.objects.filter(tenant=public_tenant).delete()
        Company.objects.create(tenant=public_tenant, name="Batch Company 1")

        result = batch_export_companies_for_rag()

        assert result["status"] == "success"
        assert result["queued_count"] >= 1
        mock_sync_task.apply_async.assert_called()

    @pytest.mark.django_db
    @patch("rag_index.tasks.db_sync_tasks.sync_model_to_rag")
    def test_batch_export_filtered_by_tenant(self, mock_sync_task, db, public_tenant):
        """Should only queue companies for specified tenant."""
        Company.objects.filter(tenant=public_tenant).delete()
        Company.objects.create(tenant=public_tenant, name="Tenant Company")

        result = batch_export_companies_for_rag(tenant_id=public_tenant.id)

        assert result["status"] == "success"
        assert result["tenant_id"] == public_tenant.id


# ── Fixtures for sync pipeline tests ────────────────────────────────


@pytest.fixture
def sample_brand_asset_for_task(db, public_tenant):
    """Create a sample BrandAsset for sync pipeline testing."""
    from onboarding.models import BrandAsset

    Company.objects.filter(tenant=public_tenant).delete()
    company = Company.objects.create(
        tenant=public_tenant,
        name="Pipeline Task Co",
    )
    return BrandAsset.objects.create(
        tenant=public_tenant,
        company=company,
        file_name="test_doc.pdf",
        file_type="document",
        file_size=2048,
        gcs_path="_landing/1/abc_test_doc.pdf",
        gcs_bucket="test-bucket",
        processed=False,
        pipeline_status="pending",
    )


@pytest.fixture
def sample_event_data(sample_brand_asset_for_task):
    """Build a sample event_data dict for the sync pipeline task."""
    asset = sample_brand_asset_for_task
    return {
        "event_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "timestamp": "2026-02-12T00:00:00+00:00",
        "source": "django-backend",
        "tenant_id": str(asset.tenant.id),
        "file_path": f"gs://test-bucket/{asset.gcs_path}",
        "file_type": "application/pdf",
        "file_size_bytes": asset.file_size,
        "raw_bucket": "test-bucket",
        "curated_bucket": "test-curated-bucket",
        "metadata": {
            "original_filename": asset.file_name,
            "asset_id": asset.id,
            "company_id": asset.company.id,
            "uploaded_at": "2026-02-12T00:00:00+00:00",
            "source_service": "onboarding",
        },
    }


# ── Stage 3: _run_indexing tests ────────────────────────────────────


class TestRunIndexing:
    """Tests for the _run_indexing helper (Stage 3)."""

    @pytest.mark.django_db
    @patch("rag_index.tasks.sync_tasks.get_orchestrator")
    @patch("rag_index.tasks.sync_tasks.run_async")
    def test_indexing_calls_orchestrator(
        self,
        mock_run_async,
        mock_get_orch,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should dispatch a SyncEvent UPSERT to the orchestrator."""
        mock_result = MagicMock()
        mock_result.operation_id = "mock-op-123"
        mock_result.processing_time_ms = 42
        mock_run_async.return_value = mock_result

        curation_result = {
            "status": "success",
            "document_id": str(uuid.uuid4()),
            "output_uri": "gs://test-curated-bucket/curated/doc.json",
        }

        result = _run_indexing(
            None,
            sample_brand_asset_for_task.id,
            str(sample_brand_asset_for_task.tenant.id),
            sample_event_data,
            curation_result,
        )

        assert result["status"] == "success"
        assert result["operation_id"] == "mock-op-123"
        mock_run_async.assert_called_once()

        # Verify asset status updated to indexed
        sample_brand_asset_for_task.refresh_from_db()
        assert sample_brand_asset_for_task.pipeline_status == "indexed"

    @pytest.mark.django_db
    def test_indexing_skipped_when_no_output_uri(
        self,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should skip indexing if curation produced no output_uri."""
        curation_result = {
            "status": "success",
            "document_id": str(uuid.uuid4()),
            "output_uri": "",
        }

        result = _run_indexing(
            None,
            sample_brand_asset_for_task.id,
            str(sample_brand_asset_for_task.tenant.id),
            sample_event_data,
            curation_result,
        )

        assert result["status"] == "skipped"

    @pytest.mark.django_db
    @patch("rag_index.tasks.sync_tasks.get_orchestrator")
    @patch("rag_index.tasks.sync_tasks.run_async")
    def test_indexing_failure_marks_asset_failed(
        self,
        mock_run_async,
        mock_get_orch,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should mark asset as failed when indexing raises."""
        mock_run_async.side_effect = Exception("Vertex AI unavailable")

        curation_result = {
            "status": "success",
            "document_id": str(uuid.uuid4()),
            "output_uri": "gs://bucket/curated/doc.json",
        }

        result = _run_indexing(
            None,
            sample_brand_asset_for_task.id,
            str(sample_brand_asset_for_task.tenant.id),
            sample_event_data,
            curation_result,
        )

        assert result["status"] == "failed"
        assert "Vertex AI unavailable" in result["error"]

        sample_brand_asset_for_task.refresh_from_db()
        assert sample_brand_asset_for_task.pipeline_status == "failed"


# ── Full sync pipeline tests ────────────────────────────────────────


class TestProcessAssetPipelineSync:
    """Tests for the full 3-stage sync pipeline Celery task."""

    @pytest.mark.django_db
    @patch("onboarding.tasks._run_indexing")
    @patch("onboarding.tasks._run_curation")
    @patch("onboarding.tasks._run_ingestion")
    def test_full_pipeline_runs_all_three_stages(
        self,
        mock_ingestion,
        mock_curation,
        mock_indexing,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should chain ingestion → curation → indexing."""
        mock_ingestion.return_value = {
            "status": "success",
            "destination_path": "gs://bucket/raw/doc.pdf",
            "trace_id": sample_event_data["trace_id"],
        }
        mock_curation.return_value = {
            "status": "success",
            "document_id": str(uuid.uuid4()),
            "output_uri": "gs://bucket/curated/doc.json",
        }
        mock_indexing.return_value = {
            "status": "success",
            "operation_id": "op-123",
        }

        result = process_asset_pipeline_sync(
            asset_id=sample_brand_asset_for_task.id,
            tenant_id=str(sample_brand_asset_for_task.tenant.id),
            event_data=sample_event_data,
        )

        assert result["status"] == "indexed"
        assert "ingestion" in result
        assert "curation" in result
        assert "indexing" in result
        mock_ingestion.assert_called_once()
        mock_curation.assert_called_once()
        mock_indexing.assert_called_once()

    @pytest.mark.django_db
    @patch("onboarding.tasks._run_curation")
    @patch("onboarding.tasks._run_ingestion")
    def test_pipeline_stops_at_ingestion_failure(
        self,
        mock_ingestion,
        mock_curation,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should stop after ingestion failure without running curation."""
        mock_ingestion.return_value = {
            "status": "failed",
            "error": "File not found in GCS",
        }

        result = process_asset_pipeline_sync(
            asset_id=sample_brand_asset_for_task.id,
            tenant_id=str(sample_brand_asset_for_task.tenant.id),
            event_data=sample_event_data,
        )

        assert result["status"] == "failed"
        mock_curation.assert_not_called()

    @pytest.mark.django_db
    @patch("onboarding.tasks._run_indexing")
    @patch("onboarding.tasks._run_curation")
    @patch("onboarding.tasks._run_ingestion")
    def test_pipeline_stops_at_curation_failure(
        self,
        mock_ingestion,
        mock_curation,
        mock_indexing,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should stop after curation failure without running indexing."""
        mock_ingestion.return_value = {
            "status": "success",
            "destination_path": "gs://bucket/raw/doc.pdf",
            "trace_id": sample_event_data["trace_id"],
        }
        mock_curation.return_value = {
            "status": "failed",
            "error": "DLP redaction failed",
        }

        result = process_asset_pipeline_sync(
            asset_id=sample_brand_asset_for_task.id,
            tenant_id=str(sample_brand_asset_for_task.tenant.id),
            event_data=sample_event_data,
        )

        assert result["status"] == "failed"
        assert "curation" in result
        mock_indexing.assert_not_called()

    @pytest.mark.django_db
    @patch("onboarding.tasks._run_indexing")
    @patch("onboarding.tasks._run_curation")
    @patch("onboarding.tasks._run_ingestion")
    def test_pipeline_returns_failed_on_indexing_failure(
        self,
        mock_ingestion,
        mock_curation,
        mock_indexing,
        sample_brand_asset_for_task,
        sample_event_data,
    ):
        """Should still report ingestion/curation when indexing fails."""
        mock_ingestion.return_value = {
            "status": "success",
            "destination_path": "gs://bucket/raw/doc.pdf",
            "trace_id": sample_event_data["trace_id"],
        }
        mock_curation.return_value = {
            "status": "success",
            "document_id": str(uuid.uuid4()),
            "output_uri": "gs://bucket/curated/doc.json",
        }
        mock_indexing.return_value = {
            "status": "failed",
            "error": "Vertex AI unreachable",
        }

        result = process_asset_pipeline_sync(
            asset_id=sample_brand_asset_for_task.id,
            tenant_id=str(sample_brand_asset_for_task.tenant.id),
            event_data=sample_event_data,
        )

        assert result["status"] == "failed"
        assert result["ingestion"]["status"] == "success"
        assert result["curation"]["status"] == "success"
        assert result["indexing"]["status"] == "failed"
