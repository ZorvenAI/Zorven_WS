"""E2E test: auto-detect intent routing (no manifest provided).

When a job is dispatched without a manifest, the RouterNode uses keyword
matching on input_prompt to select the best pipeline from available_manifests.
The executor then builds and executes the resolved manifest's full pipeline.
"""

from unittest.mock import AsyncMock, patch

from app.services.job_executor import JobExecutor

from tests.e2e.conftest import make_auto_detect_request


class TestAutoDetectRouting:
    """E2E tests for intent routing + execution in auto-detect mode."""

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_resolves_brand_analysis(
        self, mock_get_redis, mock_discovery_service
    ):
        """Input about 'brand positioning' → resolves to brand-analysis → executes."""
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

        # Pipeline actually executed (not just routing)
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_resolves_competitor_audit(
        self, mock_get_redis, mock_discovery_service
    ):
        """Input about 'competitor audit' → resolves to competitor-audit → executes."""
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
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_resolves_content_strategy(self, mock_get_redis):
        """Input about 'content strategy' → resolves to content-strategy → executes.

        content-strategy is all-internal, no external HTTP calls needed.
        """
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
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_sends_resolved_manifest_callback(
        self, mock_get_redis, mock_discovery_service
    ):
        """send_resolved_manifest callback is sent before pipeline execution."""
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
    async def test_full_pipeline_executes_after_routing(
        self, mock_get_redis, mock_discovery_service
    ):
        """Auto-detect executes full pipeline, not just routing."""
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

        # Result comes from actual pipeline execution, not stub routing
        assert "findings" in result_data
        assert len(result_data["findings"]) > 0
        # Should contain real findings from discovery, not "Auto-detect routing completed"
        assert not any(
            "auto-detect" in f.lower() for f in result_data["findings"]
        )

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_defaults_to_brand_analysis_on_ambiguous_prompt(
        self, mock_get_redis, mock_discovery_service
    ):
        """Ambiguous input → falls back to brand-analysis default → executes."""
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
        executor.callback.send_completed.assert_called_once()

    @patch("app.services.job_executor.get_redis", new_callable=AsyncMock)
    async def test_discovery_called_during_auto_detect(
        self, mock_get_redis, mock_discovery_service
    ):
        """Discovery service is called when auto-detect resolves brand-analysis."""
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

        # Discovery was actually called (brand-analysis has an external node)
        assert len(mock_discovery_service) >= 1
