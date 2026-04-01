"""
Unit tests for orchestration serializers.

Tests PipelineManifestSerializer (HLD v6.0 validation, cycle detection),
AnalysisJobCreateSerializer, AnalysisJobSerializer, and CallbackSerializer.
"""

import pytest

from orchestration.serializers import (
    AnalysisJobCreateSerializer,
    AnalysisJobSerializer,
    CallbackSerializer,
    PipelineManifestListSerializer,
    PipelineManifestSerializer,
)


@pytest.mark.django_db
class TestPipelineManifestSerializer:
    """Tests for PipelineManifestSerializer validation."""

    def test_manifest_serializer_valid(self, sample_manifest_data):
        """Valid manifest_data with nodes + edges passes validation."""
        data = {
            "pipeline_id": "valid-test",
            "name": "Valid Pipeline",
            "manifest_data": sample_manifest_data,
        }
        serializer = PipelineManifestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_manifest_serializer_missing_nodes(self):
        """Rejects manifest without nodes key."""
        data = {
            "pipeline_id": "bad-manifest",
            "name": "Bad Manifest",
            "manifest_data": {"edges": []},
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest_data" in serializer.errors

    def test_manifest_serializer_missing_edges(self):
        """Rejects manifest without edges key."""
        data = {
            "pipeline_id": "bad-manifest",
            "name": "Bad Manifest",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "a",
                        "type": "internal",
                        "handler": "NodeA",
                    }
                ]
            },
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest_data" in serializer.errors

    def test_manifest_serializer_invalid_type(self):
        """manifest_data as string rejects with ValidationError."""
        data = {
            "pipeline_id": "bad-type",
            "name": "Bad Type",
            "manifest_data": "not a dict",
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest_data" in serializer.errors

    def test_manifest_serializer_cycle_detection(self, cyclic_manifest_data):
        """Rejects circular A->B->C->A dependencies."""
        data = {
            "pipeline_id": "cyclic-test",
            "name": "Cyclic Pipeline",
            "manifest_data": cyclic_manifest_data,
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest_data" in serializer.errors
        error_msg = str(serializer.errors["manifest_data"])
        assert "circular" in error_msg.lower()

    def test_manifest_serializer_read_only_fields(self, pipeline_manifest):
        """id, version, created_at, updated_at are read-only."""
        serializer = PipelineManifestSerializer(pipeline_manifest)
        data = serializer.data
        assert "id" in data
        assert "version" in data
        assert "created_at" in data
        assert "updated_at" in data

        # Attempt to write read-only fields — they should be ignored
        update_data = {
            "pipeline_id": "updated",
            "name": "Updated",
            "version": 999,
            "manifest_data": pipeline_manifest.manifest_data,
        }
        s = PipelineManifestSerializer(
            pipeline_manifest, data=update_data, partial=True
        )
        assert s.is_valid(), s.errors
        obj = s.save()
        assert obj.version == 1  # version is read-only, not 999

    def test_manifest_list_serializer_excludes_data(self, pipeline_manifest):
        """List serializer omits manifest_data field."""
        serializer = PipelineManifestListSerializer(pipeline_manifest)
        data = serializer.data
        assert "manifest_data" not in data
        assert "pipeline_id" in data
        assert "name" in data

    def test_manifest_external_node_requires_url(self):
        """External node missing url raises ValidationError."""
        data = {
            "pipeline_id": "bad-external",
            "name": "Bad External Node",
            "manifest_data": {
                "nodes": [
                    {"id": "scraper", "type": "external"},
                ],
                "edges": [],
            },
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        error_msg = str(serializer.errors["manifest_data"])
        assert "url" in error_msg.lower()

    def test_manifest_internal_node_requires_handler(self):
        """Internal node missing handler raises ValidationError."""
        data = {
            "pipeline_id": "bad-internal",
            "name": "Bad Internal Node",
            "manifest_data": {
                "nodes": [
                    {"id": "router", "type": "internal"},
                ],
                "edges": [],
            },
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        error_msg = str(serializer.errors["manifest_data"])
        assert "handler" in error_msg.lower()

    def test_manifest_external_node_allowed_url(self):
        """External node with allowed service URL passes."""
        data = {
            "pipeline_id": "allowed-ext",
            "name": "Allowed External",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "discovery",
                        "type": "external",
                        "url": "http://discovery-agent-svc:8020/v1/search",
                    },
                ],
                "edges": [],
            },
        }
        serializer = PipelineManifestSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_manifest_external_node_disallowed_url(self):
        """External node with arbitrary URL is rejected (SSRF prevention)."""
        data = {
            "pipeline_id": "ssrf-attempt",
            "name": "SSRF Attempt",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "attacker",
                        "type": "external",
                        "url": "http://169.254.169.254/latest/meta-data/",
                    },
                ],
                "edges": [],
            },
        }
        serializer = PipelineManifestSerializer(data=data)
        assert not serializer.is_valid()
        error_msg = str(serializer.errors["manifest_data"])
        assert "allowed" in error_msg.lower()


@pytest.mark.django_db
class TestAnalysisJobCreateSerializer:
    """Tests for AnalysisJobCreateSerializer."""

    def test_job_create_serializer_valid(self, pipeline_manifest):
        """Valid manifest FK + prompt passes."""
        data = {
            "manifest": pipeline_manifest.id,
            "input_prompt": "Analyze my brand",
        }
        serializer = AnalysisJobCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_job_create_serializer_null_manifest(self):
        """Null manifest (auto-detect mode) passes validation."""
        data = {
            "manifest": None,
            "input_prompt": "Tell me about my brand",
        }
        serializer = AnalysisJobCreateSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_job_create_serializer_inactive_manifest(self, inactive_manifest):
        """Rejects reference to inactive manifest."""
        data = {
            "manifest": inactive_manifest.id,
            "input_prompt": "Test prompt",
        }
        serializer = AnalysisJobCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "manifest" in serializer.errors

    def test_job_create_serializer_empty_prompt(self, pipeline_manifest):
        """Rejects empty input_prompt."""
        data = {
            "manifest": pipeline_manifest.id,
            "input_prompt": "   ",
        }
        serializer = AnalysisJobCreateSerializer(data=data)
        assert not serializer.is_valid()
        assert "input_prompt" in serializer.errors


@pytest.mark.django_db
class TestAnalysisJobSerializer:
    """Tests for AnalysisJobSerializer computed fields."""

    def test_job_serializer_computed_fields(self, completed_job):
        """manifest_name, duration_seconds, created_by_email populated."""
        serializer = AnalysisJobSerializer(completed_job)
        data = serializer.data
        assert data["manifest_name"] == "Test Pipeline"
        assert data["duration_seconds"] is not None
        assert data["duration_seconds"] > 0
        assert data["created_by_email"] == "test@example.com"
        assert data["status"] == "completed"


@pytest.mark.django_db
class TestCallbackSerializer:
    """Tests for CallbackSerializer."""

    def test_callback_serializer_valid(self):
        """Accepts status, progress, result_data."""
        data = {
            "status": "running",
            "progress": {
                "researcher": {"status": "running"},
            },
        }
        serializer = CallbackSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_callback_serializer_partial_update(self):
        """Accepts only progress without status or result_data."""
        data = {
            "progress": {
                "researcher": {"status": "done"},
            },
        }
        serializer = CallbackSerializer(data=data)
        assert serializer.is_valid(), serializer.errors

    def test_callback_serializer_resolved_manifest(self):
        """Accepts resolved_manifest_id for intent-routed jobs."""
        data = {
            "status": "running",
            "resolved_manifest_id": "iso-brand-equity-v1",
        }
        serializer = CallbackSerializer(data=data)
        assert serializer.is_valid(), serializer.errors
        assert (
            serializer.validated_data["resolved_manifest_id"] == "iso-brand-equity-v1"
        )

    def test_callback_serializer_rejects_oversized_progress(self):
        """Rejects progress JSON exceeding 5 MB."""
        oversized = {"data": "x" * (5 * 1024 * 1024 + 1)}
        data = {"progress": oversized}
        serializer = CallbackSerializer(data=data)
        assert not serializer.is_valid()
        assert "progress" in serializer.errors

    def test_callback_serializer_rejects_oversized_result_data(self):
        """Rejects result_data JSON exceeding 5 MB."""
        oversized = {"data": "x" * (5 * 1024 * 1024 + 1)}
        data = {"result_data": oversized}
        serializer = CallbackSerializer(data=data)
        assert not serializer.is_valid()
        assert "result_data" in serializer.errors
