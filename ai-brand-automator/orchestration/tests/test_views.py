"""
Integration tests for orchestration views (RBAC, CRUD, tenant isolation).

Tests the full request/response cycle through Django middleware,
authentication, RBAC, serialization, and database writes using
DRF's APIClient.
"""

import pytest
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from orchestration.models import AnalysisJob, PipelineManifest
from tenants.models import Membership

User = get_user_model()


def _make_client(user, tenant):
    """Create an authenticated APIClient with tenant context."""
    client = APIClient()
    client.defaults["SERVER_NAME"] = "localhost"
    client.force_authenticate(user=user)
    client.defaults["HTTP_X_TENANT_ID"] = str(tenant.id)
    return client


# ── Job Endpoints — RBAC ──────────────────────────────────────────


@pytest.mark.django_db
class TestAnalysisJobViewSetRBAC:
    """Full request cycle through middleware → view → serializer → DB."""

    def test_list_jobs_viewer(self, tenant, membership_viewer, analysis_job):
        client = _make_client(membership_viewer.user, tenant)
        response = client.get("/api/v1/orchestration/jobs/")
        assert response.status_code == 200

    def test_list_jobs_editor(self, tenant, membership_editor, analysis_job):
        client = _make_client(membership_editor.user, tenant)
        response = client.get("/api/v1/orchestration/jobs/")
        assert response.status_code == 200

    def test_list_jobs_unauthenticated(self, api_client):
        response = api_client.get("/api/v1/orchestration/jobs/")
        assert response.status_code == 401

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_create_job_editor(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
    ):
        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {
                "manifest": pipeline_manifest.id,
                "input_prompt": "Analyze brand positioning",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["status"] == "queued"
        assert response.data["job_id"] is not None
        mock_delay.assert_called_once()

    def test_create_job_viewer_forbidden(
        self, tenant, membership_viewer, pipeline_manifest
    ):
        client = _make_client(membership_viewer.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {
                "manifest": pipeline_manifest.id,
                "input_prompt": "Test prompt",
            },
            format="json",
        )
        assert response.status_code == 403

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_create_job_admin(
        self,
        mock_delay,
        tenant,
        membership_admin,
        pipeline_manifest,
    ):
        client = _make_client(membership_admin.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {
                "manifest": pipeline_manifest.id,
                "input_prompt": "Admin analysis",
            },
            format="json",
        )
        assert response.status_code == 201

    def test_retrieve_job_viewer(self, tenant, membership_viewer, analysis_job):
        client = _make_client(membership_viewer.user, tenant)
        response = client.get(f"/api/v1/orchestration/jobs/{analysis_job.job_id}/")
        assert response.status_code == 200
        assert response.data["job_id"] == str(analysis_job.job_id)
        assert "progress" in response.data
        assert "result_data" in response.data

    @patch("orchestration.services.OrchestratorDispatcher.cancel")
    def test_cancel_job_editor(
        self,
        mock_cancel,
        tenant,
        membership_editor,
        running_job,
    ):
        mock_cancel.return_value = True
        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            f"/api/v1/orchestration/jobs/{running_job.job_id}/cancel/"
        )
        assert response.status_code == 200
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.FAILED
        assert "Cancelled by user" in running_job.error_message

    def test_cancel_job_viewer_forbidden(self, tenant, membership_viewer, running_job):
        client = _make_client(membership_viewer.user, tenant)
        response = client.post(
            f"/api/v1/orchestration/jobs/{running_job.job_id}/cancel/"
        )
        assert response.status_code == 403

    def test_cancel_completed_job_fails(self, tenant, membership_editor, completed_job):
        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            f"/api/v1/orchestration/jobs/{completed_job.job_id}/cancel/"
        )
        assert response.status_code == 400
        assert "cannot be cancelled" in response.data["error"].lower()


# ── Manifest Endpoints — RBAC ─────────────────────────────────────


@pytest.mark.django_db
class TestPipelineManifestViewSetRBAC:
    """Manifest CRUD RBAC enforcement."""

    def test_list_manifests_viewer(self, tenant, membership_viewer, pipeline_manifest):
        client = _make_client(membership_viewer.user, tenant)
        response = client.get("/api/v1/orchestration/manifests/")
        assert response.status_code == 200

    def test_create_manifest_admin(
        self, tenant, membership_admin, sample_manifest_data
    ):
        client = _make_client(membership_admin.user, tenant)
        response = client.post(
            "/api/v1/orchestration/manifests/",
            {
                "pipeline_id": "new-pipeline",
                "name": "New Pipeline",
                "manifest_data": sample_manifest_data,
            },
            format="json",
        )
        assert response.status_code == 201
        assert PipelineManifest.objects.filter(pipeline_id="new-pipeline").exists()

    def test_create_manifest_editor_forbidden(
        self, tenant, membership_editor, sample_manifest_data
    ):
        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/manifests/",
            {
                "pipeline_id": "forbidden-pipeline",
                "name": "Forbidden",
                "manifest_data": sample_manifest_data,
            },
            format="json",
        )
        assert response.status_code == 403

    def test_update_manifest_admin(
        self,
        tenant,
        membership_admin,
        pipeline_manifest,
        sample_manifest_data,
    ):
        client = _make_client(membership_admin.user, tenant)
        response = client.put(
            f"/api/v1/orchestration/manifests/{pipeline_manifest.id}/",
            {
                "pipeline_id": pipeline_manifest.pipeline_id,
                "name": "Updated Pipeline Name",
                "manifest_data": sample_manifest_data,
            },
            format="json",
        )
        assert response.status_code == 200
        pipeline_manifest.refresh_from_db()
        assert pipeline_manifest.name == "Updated Pipeline Name"

    def test_update_manifest_editor_forbidden(
        self,
        tenant,
        membership_editor,
        pipeline_manifest,
        sample_manifest_data,
    ):
        client = _make_client(membership_editor.user, tenant)
        response = client.put(
            f"/api/v1/orchestration/manifests/{pipeline_manifest.id}/",
            {
                "pipeline_id": pipeline_manifest.pipeline_id,
                "name": "Should Fail",
                "manifest_data": sample_manifest_data,
            },
            format="json",
        )
        assert response.status_code == 403

    def test_delete_manifest_admin_soft_deletes(
        self, tenant, membership_admin, pipeline_manifest
    ):
        client = _make_client(membership_admin.user, tenant)
        response = client.delete(
            f"/api/v1/orchestration/manifests/{pipeline_manifest.id}/"
        )
        assert response.status_code == 204
        pipeline_manifest.refresh_from_db()
        assert pipeline_manifest.is_active is False
        # Still in DB, just deactivated
        assert PipelineManifest.objects.filter(id=pipeline_manifest.id).exists()

    def test_delete_manifest_editor_forbidden(
        self, tenant, membership_editor, pipeline_manifest
    ):
        client = _make_client(membership_editor.user, tenant)
        response = client.delete(
            f"/api/v1/orchestration/manifests/{pipeline_manifest.id}/"
        )
        assert response.status_code == 403


# ── Tenant Isolation ──────────────────────────────────────────────


@pytest.mark.django_db
class TestTenantIsolation:
    """Cross-tenant data isolation tests."""

    def test_tenant_isolation_jobs(self, tenant, tenant2, analysis_job):
        """User in Tenant B cannot see Tenant A's jobs."""
        other_user = User.objects.create_user(
            username="other_user",
            email="other@test.com",
            password="TestPass123!",
        )
        Membership.objects.create(
            user=other_user,
            tenant=tenant2,
            role=Membership.Role.OWNER,
        )

        client = _make_client(other_user, tenant2)
        response = client.get("/api/v1/orchestration/jobs/")
        assert response.status_code == 200
        job_ids = [j["job_id"] for j in response.data["results"]]
        assert str(analysis_job.job_id) not in job_ids

    def test_tenant_isolation_manifests(self, tenant, tenant2, pipeline_manifest):
        """Manifests from Tenant A not visible when querying as Tenant B."""
        other_user = User.objects.create_user(
            username="manifest_user",
            email="manifest_other@test.com",
            password="TestPass123!",
        )
        Membership.objects.create(
            user=other_user,
            tenant=tenant2,
            role=Membership.Role.OWNER,
        )

        client = _make_client(other_user, tenant2)
        response = client.get("/api/v1/orchestration/manifests/")
        assert response.status_code == 200
        manifest_ids = [m["pipeline_id"] for m in response.data["results"]]
        assert pipeline_manifest.pipeline_id not in manifest_ids

    def test_backward_compat_null_tenant_jobs(self, tenant, user, membership_owner):
        """Jobs with tenant=NULL (pre-tenant data) are visible."""
        null_tenant_job = AnalysisJob.objects.create(
            tenant=None,
            manifest=None,
            input_prompt="Legacy job",
            created_by=user,
        )

        client = _make_client(user, tenant)
        response = client.get("/api/v1/orchestration/jobs/")
        assert response.status_code == 200
        job_ids = [j["job_id"] for j in response.data["results"]]
        assert str(null_tenant_job.job_id) in job_ids


# ── Job Lifecycle ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestJobLifecycle:
    """End-to-end job lifecycle through API calls."""

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_full_job_lifecycle_happy_path(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
        api_client,
    ):
        """Create → RUNNING → progress → COMPLETED → retrieve results."""
        from django.conf import settings

        # 1. Create job (as EDITOR)
        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {
                "manifest": pipeline_manifest.id,
                "input_prompt": "Analyze brand",
            },
            format="json",
        )
        assert response.status_code == 201
        job_id = response.data["job_id"]

        # 2. Callback: RUNNING
        cb_response = api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {
                "status": "running",
                "progress": {
                    "researcher": {"status": "running"},
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert cb_response.status_code == 200

        # 2b. Simulate dispatcher setting started_at
        # (normally done by OrchestratorDispatcher.dispatch on 202)
        job = AnalysisJob.objects.get(job_id=job_id)
        job.started_at = timezone.now()
        job.save(update_fields=["started_at"])

        # 3. Callback: COMPLETED with results
        result_data = {"summary": "Brand is strong", "score": 85}
        cb_response = api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {
                "status": "completed",
                "result_data": result_data,
                "progress": {
                    "researcher": {"status": "done"},
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert cb_response.status_code == 200

        # 4. Retrieve results
        response = client.get(f"/api/v1/orchestration/jobs/{job_id}/")
        assert response.status_code == 200
        assert response.data["status"] == "completed"
        assert response.data["result_data"]["score"] == 85
        assert response.data["duration_seconds"] is not None

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_full_job_lifecycle_failure(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
        api_client,
    ):
        """Create → RUNNING → FAILED → retrieve error."""
        from django.conf import settings

        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {
                "manifest": pipeline_manifest.id,
                "input_prompt": "Failing analysis",
            },
            format="json",
        )
        assert response.status_code == 201
        job_id = response.data["job_id"]

        # Callback: FAILED
        cb_response = api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {
                "status": "failed",
                "error_message": "Agent timeout",
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert cb_response.status_code == 200

        # Retrieve error
        response = client.get(f"/api/v1/orchestration/jobs/{job_id}/")
        assert response.status_code == 200
        assert response.data["status"] == "failed"
        assert "timeout" in response.data["error_message"].lower()

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_create_job_dispatches_celery_task(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
    ):
        """Verify Celery task is dispatched on job creation."""
        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {
                "manifest": pipeline_manifest.id,
                "input_prompt": "Dispatch test",
            },
            format="json",
        )
        assert response.status_code == 201
        job = AnalysisJob.objects.get(job_id=response.data["job_id"])
        mock_delay.assert_called_once_with(job.id)


# ── Redis Caching ────────────────────────────────────────────────


@pytest.mark.django_db
class TestJobStatusCaching:
    """Tests for Redis job status caching on callback and quick-status."""

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_callback_caches_status(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
        api_client,
    ):
        """Callback should cache job status in Redis."""
        from django.conf import settings
        from django.core.cache import cache

        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {"manifest": pipeline_manifest.id, "input_prompt": "Cache test"},
            format="json",
        )
        job_id = response.data["job_id"]

        # Callback: COMPLETED
        api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {"status": "completed", "result_data": {"score": 90}},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )

        cached = cache.get(f"job:status:{job_id}")
        assert cached is not None
        assert cached["status"] == "completed"
        assert cached["result_data"]["score"] == 90

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_quick_status_returns_cached(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
        api_client,
    ):
        """quick-status should return cached data without DB query."""
        from django.conf import settings

        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {"manifest": pipeline_manifest.id, "input_prompt": "Quick test"},
            format="json",
        )
        job_id = response.data["job_id"]

        # Callback to populate cache
        api_client.patch(
            f"/api/v1/orchestration/jobs/{job_id}/callback/",
            {"status": "running", "progress": {"agent1": {"status": "running"}}},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )

        # Quick status should return cached data
        response = client.get(f"/api/v1/orchestration/jobs/{job_id}/quick-status/")
        assert response.status_code == 200
        assert response.data["status"] == "running"

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_quick_status_falls_back_to_db(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
    ):
        """quick-status falls back to DB when cache is empty."""
        from django.core.cache import cache

        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {"manifest": pipeline_manifest.id, "input_prompt": "Fallback test"},
            format="json",
        )
        job_id = response.data["job_id"]

        # Ensure no cache
        cache.delete(f"job:status:{job_id}")

        response = client.get(f"/api/v1/orchestration/jobs/{job_id}/quick-status/")
        assert response.status_code == 200
        assert response.data["status"] == "queued"

    @patch("orchestration.tasks.dispatch_job_task.delay")
    def test_quick_status_bypasses_stale_inflight_cache(
        self,
        mock_delay,
        tenant,
        membership_editor,
        pipeline_manifest,
    ):
        """quick-status falls through to DB when cache has in-flight status
        but empty progress (stale entry created before callbacks arrived)."""
        from django.core.cache import cache

        client = _make_client(membership_editor.user, tenant)
        response = client.post(
            "/api/v1/orchestration/jobs/",
            {"manifest": pipeline_manifest.id, "input_prompt": "Stale test"},
            format="json",
        )
        job_id = response.data["job_id"]

        # Seed cache with in-flight status but empty progress (stale entry)
        cache.set(
            f"job:status:{job_id}",
            {"status": "running", "progress": {}},
            timeout=3600,
        )

        response = client.get(f"/api/v1/orchestration/jobs/{job_id}/quick-status/")
        assert response.status_code == 200
        # Should bypass cache and fall through to the DB, which still
        # has the job as "queued" since no real callback arrived.
        assert response.data["status"] == "queued"


# ── Callback Debug Endpoint ──────────────────────────────────────


@pytest.mark.django_db
class TestCallbackDebug:
    """Tests for the /callback-debug/ diagnostic endpoint."""

    def test_rejects_without_service_token(self, api_client):
        response = api_client.get("/api/v1/orchestration/callback-debug/")
        assert response.status_code == 403

    def test_rejects_wrong_service_token(self, api_client):
        response = api_client.get(
            "/api/v1/orchestration/callback-debug/",
            HTTP_X_SERVICE_TOKEN="wrong-token",
        )
        assert response.status_code == 403

    def test_returns_config_with_valid_token(self, api_client):
        from django.conf import settings

        response = api_client.get(
            "/api/v1/orchestration/callback-debug/",
            HTTP_X_SERVICE_TOKEN=settings.ORCHESTRATOR_SERVICE_TOKEN,
        )
        assert response.status_code == 200
        data = response.data
        assert "allowed_hosts" in data
        assert "callback_token_configured" in data
        assert "railway_private_domain" in data

    def test_does_not_leak_full_token(self, api_client):
        from django.conf import settings

        response = api_client.get(
            "/api/v1/orchestration/callback-debug/",
            HTTP_X_SERVICE_TOKEN=settings.ORCHESTRATOR_SERVICE_TOKEN,
        )
        assert response.status_code == 200
        # Should return a boolean, not the actual token value
        assert response.data["callback_token_configured"] is True
        assert settings.ORCHESTRATOR_CALLBACK_TOKEN not in str(response.data)
