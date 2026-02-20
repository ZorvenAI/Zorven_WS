"""E2E test: auto-detect intent routing (no manifest provided).

When a job is dispatched without a manifest, the RouterNode uses keyword
matching on input_prompt to select the best pipeline from available_manifests.
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_auto_detect_request


class TestAutoDetectRouting:
    """E2E tests for intent routing in auto-detect mode."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_resolves_brand_analysis(self, mock_get_redis):
        """Input about 'brand positioning' → resolves to brand-analysis."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = make_auto_detect_request(
            input_prompt="Analyze brand positioning and market analysis"
        )
        await executor.execute(request)

        executor.callback.send_resolved_manifest.assert_called_once()
        call_kwargs = executor.callback.send_resolved_manifest.call_args.kwargs
        assert call_kwargs["manifest_id"] == "brand-analysis"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_resolves_competitor_audit(self, mock_get_redis):
        """Input about 'competitor audit' → resolves to competitor-audit."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = make_auto_detect_request(
            input_prompt="Run a competitor audit and gap analysis"
        )
        await executor.execute(request)

        call_kwargs = executor.callback.send_resolved_manifest.call_args.kwargs
        assert call_kwargs["manifest_id"] == "competitor-audit"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_resolves_content_strategy(self, mock_get_redis):
        """Input about 'content strategy' → resolves to content-strategy."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = make_auto_detect_request(
            input_prompt="Create a content strategy and editorial calendar"
        )
        await executor.execute(request)

        call_kwargs = executor.callback.send_resolved_manifest.call_args.kwargs
        assert call_kwargs["manifest_id"] == "content-strategy"

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_sends_resolved_manifest_callback(self, mock_get_redis):
        """send_resolved_manifest callback is sent with the resolved pipeline ID."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = make_auto_detect_request()
        await executor.execute(request)

        executor.callback.send_resolved_manifest.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_completed_with_routing_result(self, mock_get_redis):
        """Completed callback includes resolved_manifest_id in result_data."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = make_auto_detect_request()
        await executor.execute(request)

        call_kwargs = executor.callback.send_completed.call_args.kwargs
        result_data = call_kwargs["result_data"]
        assert "resolved_manifest_id" in result_data

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_defaults_to_brand_analysis_on_ambiguous_prompt(self, mock_get_redis):
        """Ambiguous input → falls back to brand-analysis default."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_get_redis.return_value = mock_redis

        executor = JobExecutor()
        executor.callback = AsyncMock()
        executor.callback.send_running.return_value = True
        executor.callback.send_progress.return_value = True
        executor.callback.send_completed.return_value = True
        executor.callback.send_resolved_manifest.return_value = True

        request = make_auto_detect_request(
            input_prompt="Do something interesting with data"
        )
        await executor.execute(request)

        call_kwargs = executor.callback.send_resolved_manifest.call_args.kwargs
        assert call_kwargs["manifest_id"] == "brand-analysis"
