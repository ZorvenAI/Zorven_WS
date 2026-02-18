"""
Integration tests for the orchestration callback endpoint.

Tests token authentication, state transitions, intent routing resolution,
and edge cases for the service-to-service callback from
pipeline-orchestrator-svc.
"""

import pytest

from django.conf import settings

from orchestration.models import AnalysisJob


@pytest.mark.django_db
class TestCallbackEndpoint:
    """Callback endpoint: token auth + state transitions."""

    def test_callback_valid_token_progress_update(self, api_client, analysis_job):
        """Valid token + progress JSON → 200, job.progress updated."""
        url = f"/api/v1/orchestration/jobs/" f"{analysis_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={
                "status": "running",
                "progress": {
                    "researcher": {
                        "status": "running",
                        "started_at": "2026-02-17T10:00:00Z",
                    },
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING
        assert "researcher" in analysis_job.progress

    def test_callback_invalid_token(self, api_client, analysis_job):
        """Wrong token → 403, job unchanged."""
        url = f"/api/v1/orchestration/jobs/" f"{analysis_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={"status": "running"},
            format="json",
            HTTP_X_CALLBACK_TOKEN="wrong-token-value",
        )
        assert response.status_code == 403
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.QUEUED

    def test_callback_missing_token(self, api_client, analysis_job):
        """No token header → 403."""
        url = f"/api/v1/orchestration/jobs/" f"{analysis_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={"status": "running"},
            format="json",
        )
        assert response.status_code == 403

    def test_callback_sets_status_running(self, api_client, analysis_job):
        """status=running → job transitions to RUNNING."""
        url = f"/api/v1/orchestration/jobs/" f"{analysis_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={"status": "running"},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING

    def test_callback_sets_status_completed(self, api_client, running_job):
        """status=completed + result_data → stored, completed_at set."""
        url = f"/api/v1/orchestration/jobs/" f"{running_job.job_id}/callback/"
        result = {"summary": "Done", "score": 92}
        response = api_client.patch(
            url,
            data={
                "status": "completed",
                "result_data": result,
                "progress": {
                    "researcher": {"status": "done"},
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.COMPLETED
        assert running_job.result_data["score"] == 92
        assert running_job.completed_at is not None

    def test_callback_sets_status_failed(self, api_client, running_job):
        """status=failed + error_message → stored."""
        url = f"/api/v1/orchestration/jobs/" f"{running_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={
                "status": "failed",
                "error_message": "Discovery agent timeout",
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        running_job.refresh_from_db()
        assert running_job.status == AnalysisJob.Status.FAILED
        assert "timeout" in running_job.error_message.lower()
        assert running_job.completed_at is not None

    def test_callback_progress_only(self, api_client, running_job):
        """Progress-only update without status change."""
        url = f"/api/v1/orchestration/jobs/" f"{running_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={
                "progress": {
                    "researcher": {"status": "done"},
                    "strategist": {"status": "running"},
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        running_job.refresh_from_db()
        # Status unchanged
        assert running_job.status == AnalysisJob.Status.RUNNING
        assert running_job.progress["researcher"]["status"] == "done"
        assert running_job.progress["strategist"]["status"] == "running"

    def test_callback_nonexistent_job(self, api_client):
        """Callback for invalid job_id → 404."""
        url = (
            "/api/v1/orchestration/jobs/"
            "00000000-0000-0000-0000-000000000000/callback/"
        )
        response = api_client.patch(
            url,
            data={"status": "running"},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 404

    def test_callback_sets_timestamps_correctly(self, api_client, analysis_job):
        """started_at set on RUNNING transition, completed_at on COMPLETED."""
        url = f"/api/v1/orchestration/jobs/" f"{analysis_job.job_id}/callback/"

        # Transition to RUNNING — no started_at set by callback
        # (started_at is set by dispatcher, not callback)
        resp = api_client.patch(
            url,
            data={"status": "running"},
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert resp.status_code == 200

        # Transition to COMPLETED
        resp = api_client.patch(
            url,
            data={
                "status": "completed",
                "result_data": {"done": True},
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert resp.status_code == 200
        analysis_job.refresh_from_db()
        assert analysis_job.completed_at is not None

    def test_callback_resolved_manifest_updates_job(
        self, api_client, auto_detect_job, pipeline_manifest
    ):
        """resolved_manifest_id in callback updates job's manifest FK."""
        url = f"/api/v1/orchestration/jobs/" f"{auto_detect_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={
                "status": "running",
                "resolved_manifest_id": pipeline_manifest.pipeline_id,
                "progress": {
                    "intent_router": {
                        "status": "done",
                        "output": {
                            "selected_pipeline": (pipeline_manifest.pipeline_id),
                        },
                    },
                },
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        auto_detect_job.refresh_from_db()
        assert auto_detect_job.manifest == pipeline_manifest

    def test_callback_resolved_manifest_nonexistent(self, api_client, auto_detect_job):
        """resolved_manifest_id for unknown pipeline → ignored gracefully."""
        url = f"/api/v1/orchestration/jobs/" f"{auto_detect_job.job_id}/callback/"
        response = api_client.patch(
            url,
            data={
                "status": "running",
                "resolved_manifest_id": "nonexistent-pipeline",
            },
            format="json",
            HTTP_X_CALLBACK_TOKEN=settings.ORCHESTRATOR_CALLBACK_TOKEN,
        )
        assert response.status_code == 200
        auto_detect_job.refresh_from_db()
        # manifest remains None — gracefully ignored
        assert auto_detect_job.manifest is None
