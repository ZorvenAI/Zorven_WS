"""
Unit tests for OrchestratorDispatcher service.

All tests mock requests.post to avoid hitting a real orchestrator.
Tests verify payload format, tenant context, error handling,
and job status transitions.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from orchestration.models import AnalysisJob
from orchestration.services import OrchestratorDispatcher


@pytest.mark.django_db
class TestOrchestratorDispatcher:
    """Tests for OrchestratorDispatcher.dispatch()."""

    @patch("orchestration.services.requests.post")
    def test_dispatch_success(self, mock_post, analysis_job):
        """HTTP 202 → returns True, job status → RUNNING."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {"status": "accepted"}
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        result = dispatcher.dispatch(analysis_job)

        assert result is True
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.RUNNING
        assert analysis_job.started_at is not None
        mock_post.assert_called_once()

    @patch("orchestration.services.requests.post")
    def test_dispatch_connection_error(self, mock_post, analysis_job):
        """ConnectionError → returns False, job stays QUEUED."""
        mock_post.side_effect = requests.exceptions.ConnectionError(
            "Connection refused"
        )

        dispatcher = OrchestratorDispatcher()
        result = dispatcher.dispatch(analysis_job)

        assert result is False
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.QUEUED

    @patch("orchestration.services.requests.post")
    def test_dispatch_timeout(self, mock_post, analysis_job):
        """Timeout → returns False, job stays QUEUED."""
        mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

        dispatcher = OrchestratorDispatcher()
        result = dispatcher.dispatch(analysis_job)

        assert result is False
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.QUEUED

    @patch("orchestration.services.requests.post")
    def test_dispatch_http_500(self, mock_post, analysis_job):
        """HTTP 500 → returns False, job status → FAILED."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        result = dispatcher.dispatch(analysis_job)

        assert result is False
        analysis_job.refresh_from_db()
        assert analysis_job.status == AnalysisJob.Status.FAILED
        assert "500" in analysis_job.error_message

    @patch("orchestration.services.requests.post")
    def test_dispatch_payload_format(self, mock_post, analysis_job):
        """Verifies JSON payload contains required fields."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        dispatcher.dispatch(analysis_job)

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1]["json"]
        assert "job_id" in payload
        assert "manifest" in payload
        assert "input_prompt" in payload
        assert "callback_url" in payload
        assert "tenant_context" in payload
        assert payload["job_id"] == str(analysis_job.job_id)
        assert payload["input_prompt"] == "Analyze brand positioning"

    @patch("orchestration.services.requests.post")
    def test_dispatch_includes_callback_url(self, mock_post, analysis_job):
        """callback_url contains /api/v1/orchestration/jobs/{job_id}/callback/."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        dispatcher.dispatch(analysis_job)

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1]["json"]
        callback_url = payload["callback_url"]
        assert str(analysis_job.job_id) in callback_url
        assert "/api/v1/orchestration/jobs/" in callback_url
        assert callback_url.endswith("/callback/")

    @patch("orchestration.services.requests.post")
    def test_dispatch_includes_tenant_context(self, mock_post, analysis_job):
        """tenant_context contains tenant_id, gcs_raw_bucket, gcs_processed_bucket."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        dispatcher.dispatch(analysis_job)

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1]["json"]
        ctx = payload["tenant_context"]
        assert "tenant_id" in ctx
        assert "gcs_raw_bucket" in ctx
        assert "gcs_processed_bucket" in ctx

    @patch("orchestration.services.requests.post")
    def test_dispatch_null_manifest_includes_available(
        self, mock_post, auto_detect_job, pipeline_manifest
    ):
        """When job.manifest is null, payload includes available_manifests."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        dispatcher.dispatch(auto_detect_job)

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1]["json"]
        assert payload["manifest"] is None
        assert "available_manifests" in payload
        assert len(payload["available_manifests"]) >= 1

    @patch("orchestration.services.requests.post")
    def test_cancel_dispatch_success(self, mock_post, running_job):
        """Cancel sends POST to orchestrator, returns True on 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "cancelled"}
        mock_post.return_value = mock_response

        dispatcher = OrchestratorDispatcher()
        result = dispatcher.cancel(running_job)

        assert result is True
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert str(running_job.job_id) in url
        assert "/cancel" in url

    @patch("orchestration.services.requests.post")
    def test_dispatch_sets_started_at(self, mock_post, analysis_job):
        """On successful dispatch, job.started_at is set."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        assert analysis_job.started_at is None

        dispatcher = OrchestratorDispatcher()
        dispatcher.dispatch(analysis_job)

        analysis_job.refresh_from_db()
        assert analysis_job.started_at is not None

    def test_build_tenant_context_with_tenant(self, analysis_job):
        """Returns correct GCS paths for tenant."""
        dispatcher = OrchestratorDispatcher()
        ctx = dispatcher._build_tenant_context(analysis_job)
        assert ctx["tenant_id"] == str(analysis_job.tenant.id)
        assert "gcs_raw_bucket" in ctx
        assert "gcs_processed_bucket" in ctx
        assert str(analysis_job.tenant.id) in ctx["gcs_raw_bucket"]

    def test_build_tenant_context_without_tenant(self, auto_detect_job):
        """Returns empty dict when job has no tenant."""
        auto_detect_job.tenant = None
        auto_detect_job.save()

        dispatcher = OrchestratorDispatcher()
        ctx = dispatcher._build_tenant_context(auto_detect_job)
        assert ctx == {}
