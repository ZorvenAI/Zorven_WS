"""Tests for workspace views."""

import uuid
from unittest.mock import patch

import pytest
from rest_framework import status

from orchestration.models import AnalysisJob


@pytest.mark.django_db
class TestWorkflowViewSetList:
    """Tests for GET /api/v1/workspace/workflows/"""

    URL = "/api/v1/workspace/workflows/"

    def test_list_authenticated(self, authenticated_client_with_tenant, user_workflow):
        resp = authenticated_client_with_tenant.get(self.URL)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) >= 1

    def test_list_unauthenticated(self, api_client):
        resp = api_client.get(self.URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_excludes_inactive(
        self, authenticated_client_with_tenant, user_workflow
    ):
        user_workflow.is_active = False
        user_workflow.save(update_fields=["is_active"])
        resp = authenticated_client_with_tenant.get(self.URL)
        results = resp.data
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        ids = [w["workflow_id"] for w in results]
        assert str(user_workflow.workflow_id) not in ids


@pytest.mark.django_db
class TestWorkflowViewSetRetrieve:
    """Tests for GET /api/v1/workspace/workflows/{workflow_id}/"""

    def test_retrieve(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/"
        resp = authenticated_client_with_tenant.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "Test Workflow"
        assert "manifest_data" in resp.data
        assert "layout_data" in resp.data

    def test_retrieve_inactive_404(
        self, authenticated_client_with_tenant, user_workflow
    ):
        user_workflow.is_active = False
        user_workflow.save(update_fields=["is_active"])
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/"
        resp = authenticated_client_with_tenant.get(url)
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWorkflowViewSetCreate:
    """Tests for POST /api/v1/workspace/workflows/"""

    URL = "/api/v1/workspace/workflows/"

    def test_create_workflow(
        self, authenticated_client_with_tenant, sample_manifest_data
    ):
        data = {
            "name": "New Workflow",
            "description": "A brand new workflow",
            "manifest_data": sample_manifest_data,
            "layout_data": {
                "nodes": {},
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
        }
        resp = authenticated_client_with_tenant.post(self.URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "New Workflow"
        assert resp.data["workflow_id"] is not None

    def test_create_invalid_manifest(self, authenticated_client_with_tenant):
        data = {
            "name": "Bad Manifest",
            "manifest_data": {"nodes": "invalid"},
        }
        resp = authenticated_client_with_tenant.post(self.URL, data, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_viewer_denied_create(self, api_client, membership_viewer, public_tenant):
        """VIEWER role cannot create workflows."""
        api_client.force_authenticate(user=membership_viewer.user)
        api_client.defaults["SERVER_NAME"] = "localhost"
        api_client.credentials(HTTP_X_TENANT_ID=str(public_tenant.id))
        resp = api_client.post(self.URL, {}, format="json")
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestWorkflowViewSetUpdate:
    """Tests for PUT /api/v1/workspace/workflows/{workflow_id}/"""

    def test_update_name(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/"
        resp = authenticated_client_with_tenant.put(
            url, {"name": "Updated Name"}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["name"] == "Updated Name"

    def test_update_favorite(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/"
        resp = authenticated_client_with_tenant.patch(
            url, {"is_favorite": True}, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        user_workflow.refresh_from_db()
        assert user_workflow.is_favorite is True


@pytest.mark.django_db
class TestWorkflowViewSetDestroy:
    """Tests for DELETE /api/v1/workspace/workflows/{workflow_id}/"""

    def test_soft_delete(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/"
        resp = authenticated_client_with_tenant.delete(url)
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        user_workflow.refresh_from_db()
        assert user_workflow.is_active is False

    def test_viewer_denied_delete(
        self, api_client, membership_viewer, user_workflow, public_tenant
    ):
        api_client.force_authenticate(user=membership_viewer.user)
        api_client.defaults["SERVER_NAME"] = "localhost"
        api_client.credentials(HTTP_X_TENANT_ID=str(public_tenant.id))
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/"
        resp = api_client.delete(url)
        assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestWorkflowViewSetExecute:
    """Tests for POST /api/v1/workspace/workflows/{workflow_id}/execute/"""

    @patch("workspace.services.dispatch_job_task.delay")
    def test_execute(
        self, mock_dispatch, authenticated_client_with_tenant, user_workflow
    ):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/execute/"
        data = {"input_prompt": "Analyze brand positioning for Acme Corp"}
        resp = authenticated_client_with_tenant.post(url, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["status"] == "queued"
        assert mock_dispatch.called

    def test_execute_empty_prompt(
        self, authenticated_client_with_tenant, user_workflow
    ):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/execute/"
        data = {"input_prompt": ""}
        resp = authenticated_client_with_tenant.post(url, data, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    @patch("workspace.services.dispatch_job_task.delay")
    def test_concurrent_limit(
        self,
        mock_dispatch,
        authenticated_client_with_tenant,
        user_workflow,
        public_tenant,
    ):
        """PG-04: max 3 concurrent jobs."""
        # Create 3 running jobs
        for _ in range(3):
            AnalysisJob.objects.create(
                manifest=user_workflow.manifest,
                input_prompt="Running",
                tenant=public_tenant,
                status=AnalysisJob.Status.RUNNING,
            )

        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/execute/"
        data = {"input_prompt": "Fourth job"}
        resp = authenticated_client_with_tenant.post(url, data, format="json")
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestWorkflowViewSetClone:
    """Tests for POST /api/v1/workspace/workflows/{workflow_id}/clone/"""

    def test_clone(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/clone/"
        data = {"name": "Cloned Workflow"}
        resp = authenticated_client_with_tenant.post(url, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "Cloned Workflow"
        assert resp.data["workflow_id"] != str(user_workflow.workflow_id)

    def test_clone_creates_new_manifest(
        self, authenticated_client_with_tenant, user_workflow
    ):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/clone/"
        data = {"name": "Clone With New Manifest"}
        resp = authenticated_client_with_tenant.post(url, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        # The cloned workflow should have a different manifest
        assert resp.data["manifest"] != user_workflow.manifest.id


@pytest.mark.django_db
class TestWorkflowViewSetExport:
    """Tests for POST /api/v1/workspace/workflows/{workflow_id}/export/"""

    def test_export(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/export/"
        resp = authenticated_client_with_tenant.post(url)
        assert resp.status_code == status.HTTP_200_OK
        assert "manifest_data" in resp.data
        # Internal URLs should be replaced
        for node in resp.data["manifest_data"].get("nodes", []):
            if node.get("type") == "external":
                assert node["url"] == "{{SERVICE_URL}}"


@pytest.mark.django_db
class TestWorkflowViewSetImport:
    """Tests for POST /api/v1/workspace/workflows/import/"""

    URL = "/api/v1/workspace/workflows/import/"

    def test_import(self, authenticated_client_with_tenant, sample_manifest_data):
        data = {
            "name": "Imported Workflow",
            "description": "Imported from export",
            "manifest_data": sample_manifest_data,
        }
        resp = authenticated_client_with_tenant.post(self.URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["name"] == "Imported Workflow"


@pytest.mark.django_db
class TestWorkflowViewSetSnapshots:
    """Tests for GET /api/v1/workspace/workflows/{workflow_id}/snapshots/"""

    def test_list_snapshots(
        self, authenticated_client_with_tenant, user_workflow, public_tenant
    ):
        # Create a snapshot
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test",
            tenant=public_tenant,
            status=AnalysisJob.Status.COMPLETED,
        )
        from workspace.models import WorkflowSnapshot

        WorkflowSnapshot.objects.create(
            workflow=user_workflow,
            job=job,
            manifest_snapshot=user_workflow.manifest.manifest_data,
            layout_snapshot=user_workflow.layout_data,
            tenant=public_tenant,
        )

        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/snapshots/"
        resp = authenticated_client_with_tenant.get(url)
        assert resp.status_code == status.HTTP_200_OK
        # Paginated response
        assert resp.data["count"] == 1
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["chat_session_id"] is None

    def test_snapshot_includes_chat_session_id(
        self, authenticated_client_with_tenant, user_workflow, public_tenant
    ):
        """Snapshot should include chat_session_id from linked ChatWorkspaceLink."""
        job = AnalysisJob.objects.create(
            manifest=user_workflow.manifest,
            input_prompt="Test with chat",
            tenant=public_tenant,
            status=AnalysisJob.Status.COMPLETED,
        )
        from workspace.models import ChatWorkspaceLink, WorkflowSnapshot

        snapshot = WorkflowSnapshot.objects.create(
            workflow=user_workflow,
            job=job,
            manifest_snapshot=user_workflow.manifest.manifest_data,
            layout_snapshot=user_workflow.layout_data,
            tenant=public_tenant,
        )
        ChatWorkspaceLink.objects.create(
            job=job,
            workflow=user_workflow,
            snapshot=snapshot,
            chat_session_id="chat-session-xyz",
            tenant=public_tenant,
        )

        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/snapshots/"
        resp = authenticated_client_with_tenant.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["results"][0]["chat_session_id"] == "chat-session-xyz"


@pytest.mark.django_db
class TestAgentCatalog:
    """Tests for GET /api/v1/workspace/agents/"""

    URL = "/api/v1/workspace/agents/"

    def test_list_agents(self, authenticated_client):
        resp = authenticated_client.get(self.URL)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) > 0

        # Verify structure
        first = resp.data[0]
        assert "id" in first
        assert "name" in first
        assert "label" in first
        assert "type" in first
        assert "health" in first

    def test_unauthenticated(self, api_client):
        resp = api_client.get(self.URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestLinkFromChat:
    """Tests for POST /api/v1/workspace/link-from-chat/"""

    URL = "/api/v1/workspace/link-from-chat/"

    def test_link_from_chat(
        self, authenticated_client, pipeline_manifest, public_tenant, user
    ):
        job = AnalysisJob.objects.create(
            manifest=pipeline_manifest,
            input_prompt="Chat analysis",
            tenant=public_tenant,
            created_by=user,
            status=AnalysisJob.Status.COMPLETED,
            result_data={"final_response": "Done"},
        )
        data = {
            "job_id": str(job.job_id),
            "chat_session_id": "session-abc",
        }
        resp = authenticated_client.post(self.URL, data, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert "workflow_id" in resp.data

    def test_link_nonexistent_job(self, authenticated_client):
        data = {
            "job_id": str(uuid.uuid4()),
            "chat_session_id": "session-xyz",
        }
        resp = authenticated_client.post(self.URL, data, format="json")
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    def test_link_duplicate_idempotent(
        self, authenticated_client, pipeline_manifest, public_tenant, user
    ):
        """Linking the same job twice should return the existing link."""
        job = AnalysisJob.objects.create(
            manifest=pipeline_manifest,
            input_prompt="Chat",
            tenant=public_tenant,
            created_by=user,
            status=AnalysisJob.Status.COMPLETED,
        )
        data = {
            "job_id": str(job.job_id),
            "chat_session_id": "session-dup",
        }
        resp1 = authenticated_client.post(self.URL, data, format="json")
        resp2 = authenticated_client.post(self.URL, data, format="json")
        assert resp1.status_code == status.HTTP_201_CREATED
        assert resp2.status_code == status.HTTP_201_CREATED
        assert resp1.data["workflow_id"] == resp2.data["workflow_id"]


@pytest.mark.django_db
class TestWorkflowViewSetLock:
    """Tests for editing lock endpoints (Phase 2)."""

    def test_acquire_lock(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/lock/"
        resp = authenticated_client_with_tenant.post(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "acquired"

    def test_lock_info_after_acquire(
        self, authenticated_client_with_tenant, user_workflow
    ):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/lock/"
        authenticated_client_with_tenant.post(url)
        resp = authenticated_client_with_tenant.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["locked"] is True
        assert resp.data["is_mine"] is True

    def test_lock_info_unlocked(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/lock/"
        resp = authenticated_client_with_tenant.get(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["locked"] is False

    def test_release_lock(self, authenticated_client_with_tenant, user_workflow):
        url = f"/api/v1/workspace/workflows/{user_workflow.workflow_id}/lock/"
        authenticated_client_with_tenant.post(url)
        resp = authenticated_client_with_tenant.delete(url)
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["status"] == "released"


@pytest.mark.django_db
class TestWorkflowViewSetTemplates:
    """Tests for GET /api/v1/workspace/workflows/templates/"""

    URL = "/api/v1/workspace/workflows/templates/"

    def test_list_templates(self, authenticated_client_with_tenant, db):
        from orchestration.models import PipelineManifest

        PipelineManifest.objects.create(
            pipeline_id="template-view-test",
            name="Test Template",
            manifest_data={"nodes": [], "edges": []},
            tenant=None,
            is_active=True,
        )
        resp = authenticated_client_with_tenant.get(self.URL)
        assert resp.status_code == status.HTTP_200_OK
        names = [t["name"] for t in resp.data]
        assert "Test Template" in names

    def test_unauthenticated(self, api_client):
        resp = api_client.get(self.URL)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
