"""Tests for the job executor — end-to-end pipeline execution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.schemas import DispatchRequest, ManifestData, ManifestNode, TenantContext
from app.services.job_executor import JobExecutor

# Use a sentinel to distinguish "no manifest" from "explicit None"
_UNSET = object()


def _make_request(manifest=_UNSET, available_manifests=None, job_id="test-job-123"):
    """Build a DispatchRequest for testing."""
    if manifest is _UNSET:
        manifest = ManifestData(
            nodes=[
                ManifestNode(id="strategy", type="internal", handler="StrategyNode"),
                ManifestNode(id="report", type="internal", handler="ReportNode"),
            ],
            edges=[["strategy", "report"]],
            global_config={"model": "gemini-2.0-flash"},
        )

    return DispatchRequest(
        job_id=job_id,
        manifest=manifest,
        input_prompt="Analyze brand positioning for Acme Corp",
        input_context={"company_id": 42},
        tenant_context=TenantContext(
            tenant_id="1",
            gcs_raw_bucket="bucket/",
            gcs_processed_bucket="curated/",
            rag_data_store_id="ds-1",
        ),
        callback_url="http://backend:8001/api/v1/orchestration/jobs/test-job-123/callback/",
        available_manifests=available_manifests,
    )


class TestJobExecutor:
    """Test executor with mocked callback client and Redis."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_execute_simple_manifest(self, mock_get_redis):
        """Execute a 2-node manifest → completed callback."""
        # Mock Redis cancel check
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # not cancelled
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Verify "running" was sent
        executor.callback.send_running.assert_called_once()

        # Verify "completed" was sent with result_data
        executor.callback.send_completed.assert_called_once()
        call_args = executor.callback.send_completed.call_args
        assert call_args.kwargs.get("result_data") is not None

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_execute_auto_detect_mode(self, mock_get_redis):
        """Execute without manifest → intent routing → completed."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = _make_request(manifest=None)
        await executor.execute(request)

        # Verify resolved manifest was sent
        executor.callback.send_resolved_manifest.assert_called_once()

        # Verify completed was sent
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_cancel_flag_stops_execution(self, mock_get_redis):
        """Cancel flag in Redis → job fails with 'cancelled' message."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"  # cancelled!
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Verify "failed" was sent with cancel message
        executor.callback.send_failed.assert_called()
        call_args = executor.callback.send_failed.call_args
        error_msg = call_args.kwargs.get("error_message", "")
        if not error_msg and len(call_args.args) > 1:
            error_msg = call_args.args[1]
        assert "cancel" in error_msg.lower()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_invalid_manifest_sends_failed(self, mock_get_redis):
        """Invalid manifest (unknown handler) → graph build error → failed callback."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        bad_manifest = ManifestData(
            nodes=[
                ManifestNode(id="bad", type="internal", handler="UnknownNode"),
            ],
            edges=[],
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = _make_request(manifest=bad_manifest)
        await executor.execute(request)

        # Verify "failed" was sent
        executor.callback.send_failed.assert_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_progress_callbacks_sent_per_node(self, mock_get_redis):
        """Each node execution triggers a progress callback."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Should have at least 2 progress calls (one per node)
        assert executor.callback.send_progress.call_count >= 2

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_redis_failure_doesnt_crash(self, mock_get_redis):
        """Redis unavailable for cancel check → execution continues."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = _make_request()
        await executor.execute(request)

        # Should still complete (Redis failure is non-fatal for cancel check)
        executor.callback.send_completed.assert_called_once()
