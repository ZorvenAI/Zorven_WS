"""
Unit tests for orchestration models.

Tests PipelineManifest and AnalysisJob creation, constraints,
default values, and computed properties.
"""

import uuid

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from orchestration.models import AnalysisJob, PipelineManifest


@pytest.mark.django_db
class TestPipelineManifest:
    """Tests for the PipelineManifest model."""

    def test_create_pipeline_manifest(self, pipeline_manifest):
        """Create manifest with valid data, verify all fields persisted."""
        assert pipeline_manifest.pipeline_id == "test-pipeline"
        assert pipeline_manifest.name == "Test Pipeline"
        assert pipeline_manifest.version == 1
        assert pipeline_manifest.is_active is True
        assert pipeline_manifest.tenant is not None
        assert pipeline_manifest.created_by is not None
        assert "nodes" in pipeline_manifest.manifest_data
        assert "edges" in pipeline_manifest.manifest_data

    def test_manifest_unique_pipeline_version(
        self, pipeline_manifest, tenant, user, sample_manifest_data
    ):
        """UniqueConstraint(pipeline_id, version) raises IntegrityError."""
        with pytest.raises(IntegrityError):
            PipelineManifest.objects.create(
                pipeline_id="test-pipeline",
                name="Duplicate",
                manifest_data=sample_manifest_data,
                version=1,
                tenant=tenant,
                created_by=user,
            )

    def test_manifest_slug_validation(self, tenant, user, sample_manifest_data):
        """pipeline_id accepts valid slugs like brand-analysis-v1."""
        manifest = PipelineManifest.objects.create(
            pipeline_id="brand-analysis-v1",
            name="Brand Analysis",
            manifest_data=sample_manifest_data,
            tenant=tenant,
            created_by=user,
        )
        assert manifest.pipeline_id == "brand-analysis-v1"

    def test_manifest_str_representation(self, pipeline_manifest):
        """__str__ returns human-readable format."""
        expected = "Test Pipeline v1 (test-pipeline)"
        assert str(pipeline_manifest) == expected

    def test_manifest_default_version(self, tenant, user, sample_manifest_data):
        """New manifest defaults to version=1."""
        manifest = PipelineManifest.objects.create(
            pipeline_id="default-version-test",
            name="Default Version",
            manifest_data=sample_manifest_data,
            tenant=tenant,
            created_by=user,
        )
        assert manifest.version == 1

    def test_manifest_ordering(self, tenant, user, sample_manifest_data):
        """QuerySet ordered by -updated_at (most recent first)."""
        m1 = PipelineManifest.objects.create(
            pipeline_id="first",
            name="First",
            manifest_data=sample_manifest_data,
            tenant=tenant,
            created_by=user,
        )
        m2 = PipelineManifest.objects.create(
            pipeline_id="second",
            name="Second",
            manifest_data=sample_manifest_data,
            tenant=tenant,
            created_by=user,
        )
        manifests = list(PipelineManifest.objects.all())
        # Most recently updated should be first
        assert manifests[0].id == m2.id
        assert manifests[1].id == m1.id


@pytest.mark.django_db
class TestAnalysisJob:
    """Tests for the AnalysisJob model."""

    def test_create_analysis_job(self, analysis_job):
        """Create job with all required fields, verify persistence."""
        assert analysis_job.input_prompt == "Analyze brand positioning"
        assert analysis_job.tenant is not None
        assert analysis_job.manifest is not None
        assert analysis_job.created_by is not None

    def test_job_uuid_auto_generated(self, analysis_job):
        """job_id is auto-populated UUID, unique, not editable."""
        assert isinstance(analysis_job.job_id, uuid.UUID)
        assert AnalysisJob.objects.filter(job_id=analysis_job.job_id).count() == 1

    def test_job_default_status(self, analysis_job):
        """New job defaults to Status.QUEUED."""
        assert analysis_job.status == AnalysisJob.Status.QUEUED

    def test_job_duration_seconds_completed(self, completed_job):
        """Returns total_seconds() for completed job."""
        duration = completed_job.duration_seconds
        assert duration is not None
        assert duration > 0
        # Should be approximately 300 seconds (5 minutes)
        assert 290 < duration < 310

    def test_job_duration_seconds_null_when_incomplete(self, analysis_job):
        """Returns None when completed_at is null."""
        assert analysis_job.duration_seconds is None

    def test_job_manifest_protect_delete(self, pipeline_manifest, analysis_job):
        """Deleting manifest with linked jobs raises ProtectedError."""
        with pytest.raises(ProtectedError):
            pipeline_manifest.delete()
