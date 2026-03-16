"""Tests for workspace serializers."""

import pytest

from workspace.serializers import (
    WorkflowCloneSerializer,
    WorkflowCreateSerializer,
    WorkflowExecuteSerializer,
    WorkflowExportSerializer,
    WorkflowImportSerializer,
    WorkflowListSerializer,
    WorkflowUpdateSerializer,
)


@pytest.mark.django_db
class TestWorkflowCreateSerializer:
    """Tests for WorkflowCreateSerializer."""

    def test_valid_data(self, sample_manifest_data):
        data = {
            "name": "My Workflow",
            "description": "A test workflow",
            "manifest_data": sample_manifest_data,
            "layout_data": {"nodes": {}, "viewport": {"x": 0, "y": 0, "zoom": 1}},
        }
        s = WorkflowCreateSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_name_required(self, sample_manifest_data):
        data = {
            "manifest_data": sample_manifest_data,
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()
        assert "name" in s.errors

    def test_manifest_data_required(self):
        data = {"name": "My Workflow"}
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()
        assert "manifest_data" in s.errors

    def test_manifest_validation_reuse(self):
        """Manifest validation from PipelineManifestSerializer is reused."""
        data = {
            "name": "My Workflow",
            "manifest_data": {"nodes": "not a list", "edges": []},
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()
        assert "manifest_data" in s.errors

    def test_manifest_no_nodes_key(self):
        data = {
            "name": "My Workflow",
            "manifest_data": {"edges": []},
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()

    def test_manifest_no_edges_key(self):
        data = {
            "name": "My Workflow",
            "manifest_data": {"nodes": []},
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()

    def test_agent_count_cap(self):
        """IG-08: max 20 agents."""
        nodes = [
            {
                "id": f"agent_{i}",
                "type": "internal",
                "handler": "ManagerNode",
            }
            for i in range(21)
        ]
        data = {
            "name": "Too Many Agents",
            "manifest_data": {"nodes": nodes, "edges": []},
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()
        assert "manifest_data" in s.errors

    def test_duplicate_edge_prevention(self, sample_manifest_data):
        """IG-09: no duplicate edges."""
        sample_manifest_data["edges"] = [
            ["discovery", "intelligence"],
            ["discovery", "intelligence"],  # duplicate
        ]
        data = {
            "name": "Dup Edge",
            "manifest_data": sample_manifest_data,
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()
        assert "manifest_data" in s.errors

    def test_cycle_detection(self):
        """Circular dependencies are rejected."""
        data = {
            "name": "Cyclic",
            "manifest_data": {
                "nodes": [
                    {"id": "a", "type": "internal", "handler": "ManagerNode"},
                    {"id": "b", "type": "internal", "handler": "ManagerNode"},
                ],
                "edges": [["a", "b"], ["b", "a"]],
            },
        }
        s = WorkflowCreateSerializer(data=data)
        assert not s.is_valid()

    def test_name_sanitized(self, sample_manifest_data):
        """IG-07: name is sanitized."""
        data = {
            "name": "<script>alert('xss')</script>My Workflow",
            "manifest_data": sample_manifest_data,
        }
        s = WorkflowCreateSerializer(data=data)
        assert s.is_valid(), s.errors
        # The sanitized name should not contain script tags
        assert "<script>" not in s.validated_data["name"]

    def test_description_optional(self, sample_manifest_data):
        data = {
            "name": "No Desc",
            "manifest_data": sample_manifest_data,
        }
        s = WorkflowCreateSerializer(data=data)
        assert s.is_valid(), s.errors


@pytest.mark.django_db
class TestWorkflowUpdateSerializer:
    """Tests for WorkflowUpdateSerializer."""

    def test_partial_update_name_only(self):
        data = {"name": "New Name"}
        s = WorkflowUpdateSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_partial_update_favorite(self):
        data = {"is_favorite": True}
        s = WorkflowUpdateSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_update_with_manifest(self, sample_manifest_data):
        data = {"manifest_data": sample_manifest_data}
        s = WorkflowUpdateSerializer(data=data)
        assert s.is_valid(), s.errors


class TestWorkflowExecuteSerializer:
    """Tests for WorkflowExecuteSerializer."""

    def test_valid_data(self):
        data = {"input_prompt": "Analyze brand positioning"}
        s = WorkflowExecuteSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_prompt_required(self):
        data = {}
        s = WorkflowExecuteSerializer(data=data)
        assert not s.is_valid()
        assert "input_prompt" in s.errors

    def test_empty_prompt_rejected(self):
        data = {"input_prompt": "   "}
        s = WorkflowExecuteSerializer(data=data)
        assert not s.is_valid()


class TestWorkflowCloneSerializer:
    """Tests for WorkflowCloneSerializer."""

    def test_valid_name(self):
        data = {"name": "Cloned Workflow"}
        s = WorkflowCloneSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_name_required(self):
        data = {}
        s = WorkflowCloneSerializer(data=data)
        assert not s.is_valid()


@pytest.mark.django_db
class TestWorkflowExportSerializer:
    """Tests for WorkflowExportSerializer."""

    def test_export_strips_urls(self, user_workflow):
        s = WorkflowExportSerializer(user_workflow)
        data = s.data
        for node in data["manifest_data"]["nodes"]:
            if node.get("type") == "external":
                assert node["url"] == "{{SERVICE_URL}}"

    def test_export_excludes_sensitive_fields(self, user_workflow):
        s = WorkflowExportSerializer(user_workflow)
        data = s.data
        assert "tenant" not in data
        assert "created_by" not in data
        assert "workflow_id" not in data


@pytest.mark.django_db
class TestWorkflowImportSerializer:
    """Tests for WorkflowImportSerializer."""

    def test_valid_import(self, sample_manifest_data):
        data = {
            "name": "Imported Workflow",
            "manifest_data": sample_manifest_data,
        }
        s = WorkflowImportSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_import_with_placeholders(self, sample_manifest_data):
        """{{SERVICE_URL}} placeholders are accepted and preserved."""
        import copy

        manifest = copy.deepcopy(sample_manifest_data)
        for node in manifest["nodes"]:
            if node.get("type") == "external":
                node["url"] = "{{SERVICE_URL}}"

        data = {"name": "Placeholder Import", "manifest_data": manifest}
        s = WorkflowImportSerializer(data=data)
        assert s.is_valid(), s.errors

        # Verify placeholders are preserved in validated data
        validated_nodes = s.validated_data["manifest_data"]["nodes"]
        external = [n for n in validated_nodes if n["type"] == "external"]
        for node in external:
            assert node["url"] == "{{SERVICE_URL}}"

    def test_ssrf_localhost_blocked(self):
        data = {
            "name": "SSRF Test",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "evil",
                        "type": "external",
                        "url": "http://localhost:8080/steal",
                    },
                ],
                "edges": [],
            },
        }
        s = WorkflowImportSerializer(data=data)
        assert not s.is_valid()

    def test_ssrf_private_ip_blocked(self):
        data = {
            "name": "SSRF Private IP",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "evil",
                        "type": "external",
                        "url": "http://127.0.0.1:8080/steal",
                    },
                ],
                "edges": [],
            },
        }
        s = WorkflowImportSerializer(data=data)
        assert not s.is_valid()

    def test_ssrf_metadata_blocked(self):
        data = {
            "name": "SSRF Metadata",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "evil",
                        "type": "external",
                        "url": "http://169.254.169.254/latest/meta-data",
                    },
                ],
                "edges": [],
            },
        }
        s = WorkflowImportSerializer(data=data)
        assert not s.is_valid()

    def test_ssrf_gcp_metadata_blocked(self):
        data = {
            "name": "SSRF GCP Metadata",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "evil",
                        "type": "external",
                        "url": "http://metadata.google.internal/computeMetadata/v1/",
                    },
                ],
                "edges": [],
            },
        }
        s = WorkflowImportSerializer(data=data)
        assert not s.is_valid()

    def test_ssrf_private_10_range_blocked(self):
        data = {
            "name": "SSRF 10.x",
            "manifest_data": {
                "nodes": [
                    {
                        "id": "evil",
                        "type": "external",
                        "url": "http://10.0.0.1:8080/internal",
                    },
                ],
                "edges": [],
            },
        }
        s = WorkflowImportSerializer(data=data)
        assert not s.is_valid()

    def test_agent_cap_on_import(self):
        nodes = [
            {
                "id": f"agent_{i}",
                "type": "internal",
                "handler": "ManagerNode",
            }
            for i in range(21)
        ]
        data = {
            "name": "Too Many",
            "manifest_data": {"nodes": nodes, "edges": []},
        }
        s = WorkflowImportSerializer(data=data)
        assert not s.is_valid()


@pytest.mark.django_db
class TestWorkflowListSerializer:
    """Tests for WorkflowListSerializer."""

    def test_list_excludes_layout(self, user_workflow):
        s = WorkflowListSerializer(user_workflow)
        data = s.data
        assert "layout_data" not in data
        assert "manifest_data" not in data
        assert "workflow_id" in data
        assert "name" in data
