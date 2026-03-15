"""Tests for workspace services."""

import copy
from unittest.mock import MagicMock, patch

import pytest

from orchestration.models import AnalysisJob, PipelineManifest
from workspace.models import UserWorkflow, WorkflowSnapshot
from workspace.services import WorkflowService


@pytest.mark.django_db
class TestWorkflowServiceCreate:
    """Tests for WorkflowService.create_workflow."""

    def test_create_workflow(self, public_tenant, user, sample_manifest_data):
        workflow = WorkflowService.create_workflow(
            name="Service Test",
            description="Created by service",
            manifest_data=sample_manifest_data,
            layout_data={"nodes": {}, "viewport": {"x": 0, "y": 0, "zoom": 1}},
            tenant=public_tenant,
            user=user,
        )
        assert workflow.pk is not None
        assert workflow.manifest is not None
        assert workflow.manifest.manifest_data == sample_manifest_data
        assert workflow.source == UserWorkflow.Source.CREATED

    def test_create_sets_pipeline_id(self, public_tenant, user, sample_manifest_data):
        workflow = WorkflowService.create_workflow(
            name="Pipeline ID Test",
            description="",
            manifest_data=sample_manifest_data,
            layout_data={},
            tenant=public_tenant,
            user=user,
        )
        assert workflow.manifest.pipeline_id.startswith("workspace-")


@pytest.mark.django_db
class TestWorkflowServiceExecute:
    """Tests for WorkflowService.execute_workflow."""

    @patch("workspace.services.dispatch_job_task.delay")
    def test_execute_creates_job(self, mock_dispatch, user_workflow, user):
        job = WorkflowService.execute_workflow(
            workflow=user_workflow,
            input_prompt="Analyze Acme Corp",
            input_context={},
            user=user,
        )
        assert job.pk is not None
        assert job.status == AnalysisJob.Status.QUEUED
        assert job.manifest == user_workflow.manifest
        assert mock_dispatch.called

    @patch("workspace.services.dispatch_job_task.delay")
    def test_execute_creates_snapshot(self, mock_dispatch, user_workflow, user):
        job = WorkflowService.execute_workflow(
            workflow=user_workflow,
            input_prompt="Test",
            input_context={},
            user=user,
        )
        snapshot = WorkflowSnapshot.objects.get(job=job)
        assert snapshot.manifest_snapshot == user_workflow.manifest.manifest_data
        assert snapshot.layout_snapshot == user_workflow.layout_data

    @patch("workspace.services.dispatch_job_task.delay")
    def test_execute_increments_count(self, mock_dispatch, user_workflow, user):
        assert user_workflow.execution_count == 0
        WorkflowService.execute_workflow(
            workflow=user_workflow,
            input_prompt="Test",
            input_context={},
            user=user,
        )
        user_workflow.refresh_from_db()
        assert user_workflow.execution_count == 1
        assert user_workflow.last_executed_at is not None

    def test_concurrent_limit(self, user_workflow, user, public_tenant):
        """PG-04: raises ValueError when limit exceeded."""
        for _ in range(3):
            AnalysisJob.objects.create(
                manifest=user_workflow.manifest,
                input_prompt="Running",
                tenant=public_tenant,
                status=AnalysisJob.Status.RUNNING,
            )

        with pytest.raises(ValueError, match="Concurrent execution limit"):
            WorkflowService.execute_workflow(
                workflow=user_workflow,
                input_prompt="Fourth",
                input_context={},
                user=user,
            )


@pytest.mark.django_db
class TestWorkflowServiceClone:
    """Tests for WorkflowService.clone_workflow."""

    def test_clone_creates_new_manifest(self, user_workflow, public_tenant, user):
        cloned = WorkflowService.clone_workflow(
            source_workflow=user_workflow,
            new_name="Clone",
            tenant=public_tenant,
            user=user,
        )
        assert cloned.manifest.id != user_workflow.manifest.id
        assert cloned.manifest.manifest_data == user_workflow.manifest.manifest_data

    def test_clone_independent_manifest(self, user_workflow, public_tenant, user):
        """Editing the clone's manifest doesn't affect the original."""
        cloned = WorkflowService.clone_workflow(
            source_workflow=user_workflow,
            new_name="Independent Clone",
            tenant=public_tenant,
            user=user,
        )
        cloned.manifest.manifest_data["nodes"].append(
            {"id": "new", "type": "internal", "handler": "ManagerNode"}
        )
        cloned.manifest.save()

        user_workflow.manifest.refresh_from_db()
        node_ids = [n["id"] for n in user_workflow.manifest.manifest_data["nodes"]]
        assert "new" not in node_ids

    def test_clone_source_is_cloned(self, user_workflow, public_tenant, user):
        cloned = WorkflowService.clone_workflow(
            source_workflow=user_workflow,
            new_name="Clone Source Test",
            tenant=public_tenant,
            user=user,
        )
        assert cloned.source == UserWorkflow.Source.CLONED


@pytest.mark.django_db
class TestWorkflowServiceExport:
    """Tests for WorkflowService.export_workflow."""

    def test_export_strips_urls(self, user_workflow):
        data = WorkflowService.export_workflow(user_workflow)
        for node in data["manifest_data"]["nodes"]:
            if node.get("type") == "external":
                assert node["url"] == "{{SERVICE_URL}}"

    def test_export_includes_metadata(self, user_workflow):
        data = WorkflowService.export_workflow(user_workflow)
        assert "name" in data
        assert "description" in data
        assert "exported_at" in data

    def test_export_excludes_tenant(self, user_workflow):
        data = WorkflowService.export_workflow(user_workflow)
        assert "tenant" not in data
        assert "created_by" not in data


@pytest.mark.django_db
class TestWorkflowServiceImport:
    """Tests for WorkflowService.import_workflow."""

    def test_import_resolves_placeholders(
        self, public_tenant, user, sample_manifest_data
    ):
        # Replace URLs with placeholders
        import_data = copy.deepcopy(sample_manifest_data)
        for node in import_data["nodes"]:
            if node.get("type") == "external":
                node["url"] = "{{SERVICE_URL}}"

        workflow = WorkflowService.import_workflow(
            name="Imported",
            description="",
            manifest_data=import_data,
            layout_data={},
            tenant=public_tenant,
            user=user,
        )
        # Check that discovery node got its URL back
        nodes = workflow.manifest.manifest_data["nodes"]
        discovery = next(n for n in nodes if n["id"] == "discovery")
        assert discovery["url"] != "{{SERVICE_URL}}"
        assert "discovery-agent-svc" in discovery["url"]


@pytest.mark.django_db
class TestWorkflowServiceLinkFromChat:
    """Tests for WorkflowService.link_from_chat."""

    def test_link_creates_workflow_and_snapshot(
        self, pipeline_manifest, public_tenant, user
    ):
        job = AnalysisJob.objects.create(
            manifest=pipeline_manifest,
            input_prompt="Chat test",
            tenant=public_tenant,
            created_by=user,
            status=AnalysisJob.Status.COMPLETED,
        )
        link = WorkflowService.link_from_chat(
            job=job,
            chat_session_id="sess-1",
            tenant=public_tenant,
        )
        assert link.workflow is not None
        assert link.snapshot is not None
        assert link.chat_session_id == "sess-1"

    def test_link_idempotent(self, pipeline_manifest, public_tenant, user):
        job = AnalysisJob.objects.create(
            manifest=pipeline_manifest,
            input_prompt="Chat dup",
            tenant=public_tenant,
            created_by=user,
        )
        link1 = WorkflowService.link_from_chat(
            job=job, chat_session_id="s1", tenant=public_tenant
        )
        link2 = WorkflowService.link_from_chat(
            job=job, chat_session_id="s1", tenant=public_tenant
        )
        assert link1.pk == link2.pk

    def test_link_no_manifest_raises(self, public_tenant, user):
        job = AnalysisJob.objects.create(
            input_prompt="No manifest",
            tenant=public_tenant,
            created_by=user,
        )
        with pytest.raises(ValueError, match="without a manifest"):
            WorkflowService.link_from_chat(
                job=job, chat_session_id="s", tenant=public_tenant
            )


@pytest.mark.django_db
class TestWorkflowServiceDashboardData:
    """Tests for WorkflowService.extract_dashboard_data."""

    def test_empty_result(self):
        data = WorkflowService.extract_dashboard_data(None)
        assert data == {"typed": {}, "generic": {}}

    def test_extracts_voc_metrics(self):
        result = {
            "node_results": {
                "voice_of_customer": {
                    "voc_health_score": 78,
                    "nps_analysis": {
                        "nps_available": True,
                        "current_nps": {"nps_score": 42},
                    },
                    "sentiment": {
                        "overall_sentiment": {
                            "positive": 0.6,
                            "neutral": 0.3,
                            "negative": 0.1,
                        }
                    },
                    "pain_point_priority_matrix": {
                        "pain_points": [{"name": "p1"}, {"name": "p2"}]
                    },
                    "confidence_score": 0.85,
                }
            }
        }
        data = WorkflowService.extract_dashboard_data(result)
        assert data["typed"]["voc_health_score"] == 78
        assert data["typed"]["nps"] == 42
        assert data["typed"]["sentiment_trend"] == "positive"
        assert data["typed"]["pain_points_count"] == 2
        assert data["typed"]["confidence_score"] == 0.85

    def test_extracts_trend_metrics(self):
        result = {
            "node_results": {
                "trend_cultural": {
                    "scored_trends": [{"topic": "AI"}, {"topic": "ESG"}],
                }
            }
        }
        data = WorkflowService.extract_dashboard_data(result)
        assert data["typed"]["trends_identified"] == 2


@pytest.mark.django_db
class TestWorkflowServiceTemplates:
    """Tests for WorkflowService.get_templates."""

    def test_returns_system_templates(self, db):
        PipelineManifest.objects.create(
            pipeline_id="template-1",
            name="System Template",
            manifest_data={"nodes": [], "edges": []},
            tenant=None,  # system template
            is_active=True,
        )
        templates = WorkflowService.get_templates()
        assert templates.count() >= 1

    def test_excludes_inactive(self, db):
        PipelineManifest.objects.create(
            pipeline_id="template-inactive",
            name="Inactive Template",
            manifest_data={"nodes": [], "edges": []},
            tenant=None,
            is_active=False,
        )
        templates = WorkflowService.get_templates()
        names = [t.name for t in templates]
        assert "Inactive Template" not in names


@pytest.mark.django_db
class TestWorkflowServiceUpdate:
    """Tests for WorkflowService.update_workflow."""

    def test_update_name(self, user_workflow):
        WorkflowService.update_workflow(user_workflow, {"name": "Updated"})
        user_workflow.refresh_from_db()
        assert user_workflow.name == "Updated"
        assert user_workflow.manifest.name == "Updated"

    def test_update_manifest_data(self, user_workflow, sample_manifest_data):
        new_data = copy.deepcopy(sample_manifest_data)
        new_data["global_config"]["temperature"] = 0.5
        WorkflowService.update_workflow(user_workflow, {"manifest_data": new_data})
        user_workflow.manifest.refresh_from_db()
        assert (
            user_workflow.manifest.manifest_data["global_config"]["temperature"] == 0.5
        )

    def test_update_favorite(self, user_workflow):
        WorkflowService.update_workflow(user_workflow, {"is_favorite": True})
        user_workflow.refresh_from_db()
        assert user_workflow.is_favorite is True


@pytest.mark.django_db
class TestWorkflowServiceLock:
    """Tests for WorkflowService editing lock (Phase 2)."""

    def test_acquire_lock(self, user_workflow, user):
        acquired = WorkflowService.acquire_editing_lock(
            workflow_id=str(user_workflow.workflow_id),
            tenant_id=0,
            user=user,
        )
        assert acquired is True

    def test_acquire_lock_same_user_refreshes(self, user_workflow, user):
        wid = str(user_workflow.workflow_id)
        WorkflowService.acquire_editing_lock(wid, 0, user)
        acquired = WorkflowService.acquire_editing_lock(wid, 0, user)
        assert acquired is True

    def test_acquire_lock_different_user_denied(
        self, user_workflow, user, django_user_model
    ):
        other = django_user_model.objects.create_user(
            username="other", email="other@test.com", password="pass"
        )
        wid = str(user_workflow.workflow_id)
        WorkflowService.acquire_editing_lock(wid, 0, user)
        acquired = WorkflowService.acquire_editing_lock(wid, 0, other)
        assert acquired is False

    def test_release_lock(self, user_workflow, user):
        wid = str(user_workflow.workflow_id)
        WorkflowService.acquire_editing_lock(wid, 0, user)
        released = WorkflowService.release_editing_lock(wid, 0, user)
        assert released is True
        assert WorkflowService.get_lock_info(wid, 0) is None

    def test_release_lock_wrong_user(self, user_workflow, user, django_user_model):
        other = django_user_model.objects.create_user(
            username="other2", email="other2@test.com", password="pass"
        )
        wid = str(user_workflow.workflow_id)
        WorkflowService.acquire_editing_lock(wid, 0, user)
        released = WorkflowService.release_editing_lock(wid, 0, other)
        assert released is False

    def test_force_release_lock(self, user_workflow, user):
        wid = str(user_workflow.workflow_id)
        WorkflowService.acquire_editing_lock(wid, 0, user)
        WorkflowService.force_release_lock(wid, 0)
        assert WorkflowService.get_lock_info(wid, 0) is None

    def test_get_lock_info(self, user_workflow, user):
        wid = str(user_workflow.workflow_id)
        WorkflowService.acquire_editing_lock(wid, 0, user)
        info = WorkflowService.get_lock_info(wid, 0)
        assert info is not None
        assert info["user_email"] == user.email

    def test_get_lock_info_unlocked(self, user_workflow):
        wid = str(user_workflow.workflow_id)
        info = WorkflowService.get_lock_info(wid, 0)
        assert info is None


class TestAgentCatalog:
    """Tests for WorkflowService.get_agent_catalog with health checks."""

    def test_internal_agents_always_healthy(self):
        with patch("workspace.services.EXTERNAL_AGENTS", []):
            catalog = WorkflowService.get_agent_catalog()
            for entry in catalog:
                assert entry["health"] == "healthy"

    def test_external_agents_cached_health(self):
        with patch("workspace.services.cache") as mock_cache:
            mock_cache.get.return_value = "healthy"
            catalog = WorkflowService.get_agent_catalog()
            external = [e for e in catalog if e["type"] == "external"]
            assert len(external) > 0
            for entry in external:
                assert entry["health"] == "healthy"

    @patch("workspace.services.WorkflowService._check_single_agent_health")
    def test_external_agents_uncached_parallel_check(self, mock_check):
        mock_check.return_value = ("discovery", "healthy")
        with patch("workspace.services.cache") as mock_cache:
            mock_cache.get.return_value = None
            with patch(
                "workspace.services.EXTERNAL_AGENTS",
                [
                    {
                        "id": "discovery",
                        "name": "discovery",
                        "label": "Web Discovery",
                        "description": "Test",
                        "type": "external",
                        "url": "http://discovery:8020/v1/execute",
                        "icon": "search",
                    }
                ],
            ):
                catalog = WorkflowService.get_agent_catalog()
                external = [e for e in catalog if e["type"] == "external"]
                assert external[0]["health"] == "healthy"
                mock_cache.set.assert_called()

    @patch("workspace.services.httpx.get")
    def test_check_single_agent_health_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        agent_id, status = WorkflowService._check_single_agent_health(
            "discovery", "http://discovery:8020/health"
        )
        assert agent_id == "discovery"
        assert status == "healthy"

    @patch("workspace.services.httpx.get")
    def test_check_single_agent_health_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        agent_id, status = WorkflowService._check_single_agent_health(
            "discovery", "http://discovery:8020/health"
        )
        assert status == "unhealthy"

    @patch("workspace.services.httpx.get")
    def test_check_single_agent_health_timeout(self, mock_get):
        mock_get.side_effect = Exception("Connection timeout")
        agent_id, status = WorkflowService._check_single_agent_health(
            "discovery", "http://discovery:8020/health"
        )
        assert status == "unhealthy"

    def test_derive_health_url(self):
        url = WorkflowService._derive_health_url(
            "http://discovery-agent-svc:8020/v1/execute"
        )
        assert url == "http://discovery-agent-svc:8020/health"

    def test_derive_health_url_with_path(self):
        url = WorkflowService._derive_health_url(
            "http://market-research-agent-svc:8021/v1/execute"
        )
        assert url == "http://market-research-agent-svc:8021/health"
