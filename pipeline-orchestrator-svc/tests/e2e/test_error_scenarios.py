"""E2E test: error handling and graceful degradation.

Tests that the pipeline handles failures in external services, Redis,
callbacks, and invalid manifests without crashing.
"""

from unittest.mock import AsyncMock, patch

import httpx

from app.api.schemas import ManifestData, ManifestNode
from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_dispatch_request


class TestDiscoveryServiceDown:
    """Pipeline completes even when discovery service is unavailable."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_discovery_500_pipeline_still_completes(
        self, mock_get_redis, brand_analysis_manifest, httpx_mock
    ):
        """Discovery returns 500 → ExternalWrapper uses stub → pipeline completes."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        # Register 500 response for discovery
        httpx_mock.add_response(
            url="http://discovery-agent-svc:8020/v1/search",
            method="POST",
            status_code=500,
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        # Pipeline should complete, not fail
        executor.callback.send_completed.assert_called_once()
        executor.callback.send_failed.assert_not_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_discovery_connection_refused_pipeline_completes(
        self, mock_get_redis, brand_analysis_manifest, httpx_mock
    ):
        """Discovery unreachable → stub fallback → pipeline completes."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="http://discovery-agent-svc:8020/v1/search",
            method="POST",
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        executor.callback.send_completed.assert_called_once()


class TestCancelFlag:
    """Cancel flag in Redis stops pipeline execution."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_cancel_flag_stops_pipeline(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Redis cancel flag set → job fails with 'cancelled' message."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "1"  # cancelled!
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()
        call_kwargs = executor.callback.send_failed.call_args.kwargs
        error_msg = call_kwargs.get("error_message", "")
        assert "cancel" in error_msg.lower()


class TestInvalidManifest:
    """Invalid manifests send failed callback."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_unknown_handler_sends_failed(self, mock_get_redis):
        """Manifest with unknown handler → graph build error → failed callback."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        bad_manifest = ManifestData(
            nodes=[
                ManifestNode(id="bad_node", type="internal", handler="NonExistentNode"),
            ],
            edges=[],
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = make_dispatch_request(bad_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_cyclic_manifest_sends_failed(self, mock_get_redis):
        """Manifest with cycle → graph build error → failed callback."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        cyclic_manifest = ManifestData(
            nodes=[
                ManifestNode(id="a", type="internal", handler="StrategyNode"),
                ManifestNode(id="b", type="internal", handler="ReportNode"),
            ],
            edges=[["a", "b"], ["b", "a"]],
        )

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_failed.return_value = True

        request = make_dispatch_request(cyclic_manifest)
        await executor.execute(request)

        executor.callback.send_failed.assert_called()


class TestRedisUnavailable:
    """Redis failure doesn't crash the pipeline."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_redis_error_pipeline_continues(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Redis throws exception on cancel check → execution continues."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = Exception("Redis down")
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        await executor.execute(request)

        # Pipeline completes despite Redis being unavailable
        executor.callback.send_completed.assert_called_once()


class TestCallbackFailure:
    """Callback failures don't crash the executor."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_callback_error_does_not_crash(
        self, mock_get_redis, brand_analysis_manifest, mock_discovery_service
    ):
        """Callback send_running raises → executor handles gracefully."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        # send_running succeeds but send_completed fails
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.side_effect = Exception(
            "Callback URL unreachable"
        )
        executor.callback.send_failed.return_value = True

        request = make_dispatch_request(brand_analysis_manifest)
        # Should not raise — executor catches callback errors
        await executor.execute(request)
